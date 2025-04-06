import sys,os,time,traceback,functools,json,ctypes
from warnings import warn
from threading import Thread,Lock,current_thread
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as msgbox
import tkinter.scrolledtext as scrolledtext
from model_api import Session,SIDER_MODELS,SIDER_ADVANCED_MODELS,\
                      DEEPSEEK_MODELS,APIRequestError,SIDER_TOKEN_FILE,\
                      OPENAI_TOKEN_FILE,DEEPSEEK_TOKEN_FILE
from selenium_login import login,default_token_getter,deepseek_token_getter
if sys.platform == "win32":import winsound
else:winsound = None

CHAT_MODES={
    "聊天":Session.chat,
    "搜索":Session.search,
    "翻译":Session.translate,
    "语法检查 (英文)":Session.improve_grammar,
}
ICON_FILE="res/sider.ico"
SIDER_LOGIN_URL="https://sider.ai/login"
DEEPSEEK_LOGIN_URL="https://chat.deepseek.com/sign_in"

class RedirectedStream:
    def __init__(self,text,tag,autoflush=False):
        self.text=text
        self.tag=tag
        self.autoflush=autoflush
    def write(self,string):
        self.text.insert(tk.END,string,self.tag) # 输出文字
        #self.text.mark_set("insert",END) # 将光标移到文本末尾，以显示新输出的内容
        if self.autoflush:self.flush()
    def flush(self):
        self.text.see(tk.END) # self.text.yview('moveto',1)
        self.text.update()

class ScrolledText(scrolledtext.ScrolledText):
    # 避免文本框的state属性为DISABLED时，无法插入和删除
    def __init__(self,*args,**kw):
        self.__super=super() # 提高性能
        self.__super.__init__(*args,**kw)
    # pylint: disable=no-self-argument, no-member
    def _wrapper(func):
        @functools.wraps(func)
        def inner(self,*args,**kw):
            disabled = self["state"]==tk.DISABLED
            if disabled:
                self.config(state=tk.NORMAL)
            result=getattr(self.__super,func.__name__)(*args,**kw)
            if disabled:
                self.config(state=tk.DISABLED)
            return result
        return inner
    @_wrapper
    def insert(self,*args,**kw):pass
    @_wrapper
    def delete(self,*args,**kw):pass

class AccountManager(tk.Toplevel):
    def __init__(self,master,first=False):
        self.master=master
        self.destroyed=False
        self.first=first # 是否为第一次添加账号
    def show(self):
        super().__init__(self.master)
        self.protocol("WM_DELETE_WINDOW",self.quit)
        self.geometry("800x660")
        # 当父窗口最小化后，自身也跟随父窗口最小化
        self.transient(self.master)

        if sys.platform=="win32":
            self.attributes("-toolwindow",True)
        self.attributes("-topmost",True)
        self.bind("<FocusIn>",lambda event:self.attributes("-topmost",True))
        self.bind("<FocusOut>",lambda event:self.attributes("-topmost",False))

        login_text = "重新登录" if not self.first else "登录"
        lbl_sider=ttk.LabelFrame(self,text="Sider")
        btn_sider=ttk.Button(lbl_sider,text=f"\n{login_text}\n",
            command=lambda:self.login(btn_sider,
                                      SIDER_LOGIN_URL, SIDER_TOKEN_FILE,
                                      default_token_getter))
        btn_sider.pack(fill=tk.X)
        lbl_sider.pack(side=tk.TOP,fill=tk.X)

        lbl_deepseek=ttk.LabelFrame(self,text="DeepSeek (网页版)")
        btn_deepseek=ttk.Button(lbl_deepseek,text=f"\n{login_text}\n",
            command=lambda:self.login(btn_deepseek,
                                      DEEPSEEK_LOGIN_URL, DEEPSEEK_TOKEN_FILE,
                                      deepseek_token_getter))
        btn_deepseek.pack(fill=tk.X)
        lbl_deepseek.pack(side=tk.TOP,fill=tk.X)

        frame_apikeys=ttk.LabelFrame(self,text="API Key编辑")
        self.contentvar={} # 存放每个模型的StringVar
        for model in self.master.session.openai.models:
            frame=tk.Frame(frame_apikeys)
            tk.Label(frame,text=f"{self.master.model_name_to_friendly_name.get(model,model)}: ",
                     width=18).pack(side=tk.LEFT)
            self.contentvar[model]=tk.StringVar(
                value=self.master.session.openai.models[model]["api_key"])
            ttk.Entry(frame,textvariable=self.contentvar[model])\
                .pack(side=tk.RIGHT,expand=True,fill=tk.X)

            frame.pack(side=tk.TOP,fill=tk.X)
        frame_apikeys.pack(side=tk.TOP,expand=True,fill=tk.BOTH)

        buttons=tk.Frame(self)
        ttk.Button(buttons,text="确定",width=6,command=self.save).pack(
            side=tk.LEFT,padx=12)
        ttk.Button(buttons,text="取消",width=6,command=self.destroy).pack(
            side=tk.LEFT,padx=12)
        buttons.pack(side=tk.RIGHT,pady=2)
    def quit(self):
        self.destroyed=True # 标记自身已关闭
        self.destroy()
    def save(self):
        with open(OPENAI_TOKEN_FILE,encoding="utf-8") as f:
            config=json.load(f)
        # 更新配置中的api key
        for model,var in self.contentvar.items():
            api_key=var.get()
            for item in config:
                if item["name"]==model: # 找到模型
                    item["api_key"]=api_key
        with open(OPENAI_TOKEN_FILE,"w",encoding="utf-8") as f:
            json.dump(config,f)
        self.master.session.openai.reset_config() # 重新加载配置文件
        print("账号配置已更新")
        self.destroy()
    def login(self, btn, url, data_path, token_getter):
        def done():
            if not self.destroyed:
                btn.config(state=tk.NORMAL)
            master=self if not self.destroyed else self.master
            msgbox.showinfo("提示","登录完成",parent=master)
            self.master.new_chat(clear_display=False) # 重新加载token
        def fail(reason):
            if not self.destroyed:
                btn.config(state=tk.NORMAL)
            master=self if not self.destroyed else self.master
            msgbox.showinfo("错误",reason,parent=master)

        self.master.set_running(True)
        btn["state"]=tk.DISABLED
        t=Thread(target=login,args=(
            url,data_path,token_getter,
            self.master.is_running,
            done,fail))
        t.start()

def check_no_token(session):
    # 检查session是否完全不包含token或api key
    if session.sider.token:
        return False
    if session.deepseek.token:
        return False
    if any(model["api_key"] for model in session.openai.models.values()):
        return False
    return True

SEPARATOR="---"
class SiderGUI(tk.Tk):
    TITLE="多合一AI聊天助手"
    FONT=(None,11,"normal")
    def __init__(self,update_sider_info_at_init=True):
        super().__init__()
        if os.path.isfile(ICON_FILE):
            self.iconbitmap(ICON_FILE)
        self.title(self.TITLE)
        self.geometry("1000x800")  # 设置窗口大小
        self.protocol("WM_DELETE_WINDOW", self.quit)

        # 初始化属性、默认设置以及session
        self.model="gpt-4o-mini (sider)"
        self.mode_func=Session.chat
        self.original_stdout=self.original_stderr=None
        self.session = Session(update_info_at_init=False)
        self._running=False
        self._lock=Lock()
        self.threads=[]

        top_frame=tk.Frame(self)
        top_frame.pack(side=tk.TOP,fill=tk.X)
        self.lbl_remain=tk.Label(top_frame)
        self.lbl_remain.pack(side=tk.RIGHT)

        # 创建主聊天记录框
        self.chat_display = ScrolledText(self,wrap=tk.WORD,state=tk.DISABLED,font=self.FONT)
        self.chat_display.tag_config("ai_resp", justify="left")
        self.chat_display.tag_config("user", justify="right")
        self.chat_display.tag_config("output", justify="left")
        self.chat_display.tag_config("error", justify="left", foreground="red")

        # 创建用户输入框
        self.user_input = ScrolledText(self, wrap=tk.WORD, height=5, font=self.FONT)

        bottom_frame = tk.Frame(self)
        style = ttk.Style()
        style.configure("TMenubutton", background="#CCCCCC") # 设置OptionMenu为灰色

        mode_var=tk.StringVar()
        default_mode=[k for k,v in CHAT_MODES.items() if v == self.mode_func][0]
        self.mode_select = ttk.OptionMenu(bottom_frame, mode_var, default_mode, *tuple(CHAT_MODES),
                                command=lambda event:setattr(self,"mode_func",CHAT_MODES[mode_var.get()]))
        self.mode_select.pack(side=tk.LEFT, padx=5)
        model_var=tk.StringVar()
        openai_models=[] # openai风格接口的模型
        self.model_name_map={} # 将用户友好名称和实际名称对应
        self.model_name_to_friendly_name={}
        for name,model in self.session.openai.models.items():
            if "user_friendly_name" in model:
                self.model_name_map[model["user_friendly_name"]]=name
                self.model_name_to_friendly_name[name]=model["user_friendly_name"]
                openai_models.append(model["user_friendly_name"])
            else:
                openai_models.append(name)
        models=[f"{model} (sider)" for model in SIDER_MODELS] + \
               openai_models + DEEPSEEK_MODELS + [SEPARATOR] + \
               [f"{model} (sider)" for model in SIDER_ADVANCED_MODELS]
        def on_select_model(event):
            model=model_var.get()
            if model==SEPARATOR:
                msgbox.showinfo("",f"无效选项: {model}，请重新选择!",parent=self)
            model_name=self.model_name_map.get(model,model)
            self.model=model_name
        self.model_select = ttk.OptionMenu(bottom_frame, model_var, self.model, *models,
                                           command=on_select_model)
        self.model_select.pack(side=tk.LEFT, padx=5)

        self.send_button = ttk.Button(bottom_frame, text="发送",
                                      command=self.send_message,width=6)
        self.bind_all("<Control-Return>",self.send_message)
        self.send_button.pack(side=tk.RIGHT, padx=5)

        self.new_chat_button = ttk.Button(bottom_frame, text="新对话",
                                          command=self.new_chat,width=6)
        self.new_chat_button.pack(side=tk.RIGHT, padx=5)
        self.stop_button = ttk.Button(bottom_frame, text="停止",
                                      command=lambda:self.set_running(False),width=6)
        self.stop_button.pack(side=tk.RIGHT, padx=5)
        self.manage_button = ttk.Button(bottom_frame, text="账号管理",
                                          command=self.show_account_manager,width=8)
        self.manage_button.pack(side=tk.RIGHT, padx=5)

        bottom_frame.pack(side=tk.BOTTOM,fill=tk.X)
        self.user_input.pack(side=tk.BOTTOM,fill=tk.X)
        self.chat_display.pack(side=tk.TOP, expand=True, fill=tk.BOTH)
        self.redirect_stream()
        self.update()

        if update_sider_info_at_init:
            t=Thread(target=self.update_info_at_init_thread)
            t.start()
        if check_no_token(self.session):
            msgbox.showinfo("提示","初次使用，请登录或添加API Key!")
            self.show_account_manager(first=True)
    def update_info_at_init_thread(self):
        try:
            self.session.update_userinfo()
        except Exception as err:
            pass #warn(f"Failed to get user info ({type(err).__name__}): {err}")
        self.update_remain()
    def is_running(self):
        # 获取当前是否运行 (线程安全)
        with self._lock:
            return self._running
    def set_running(self,state):
        # 设置当前是否运行 (线程安全)
        with self._lock:
            self._running=state
    def redirect_stream(self): # 重定向sys.stdout和sys.stderr
        self.original_stdout=sys.stdout
        self.original_stderr=sys.stderr
        sys.stdout=RedirectedStream(self.chat_display,"output")
        sys.stderr=RedirectedStream(self.chat_display,"error")
    def reset_stream(self):
        sys.stdout=self.original_stdout
        sys.stderr=self.original_stderr
    def quit(self):
        self.set_running(False)
        #for thread in self.threads:
        #    thread.join()
        self.reset_stream()
        self.destroy()

    def update_remain(self):
        self.lbl_remain["text"]=f"""Sider 基础: 剩余 {self.session.remain or 0}/{self.session.total or 0} \
高级: 剩余 {self.session.advanced_remain or 0}/{self.session.advanced_total or 0}"""

    def new_chat(self, clear_display = True):
        # 开始新对话，并清空聊天记录
        if clear_display:
            self.chat_display.delete(1.0, tk.END)
        self.session=Session(update_info_at_init=False)
    def show_account_manager(self, first = False):
        AccountManager(self, first).show()

    def send_message(self,event=None):
        if str(self.send_button["state"])==tk.DISABLED:return # 对于Ctrl+Enter

        # 发送内容并显示AI的回复
        user_message = self.user_input.get(1.0, tk.END).strip()
        if not user_message:return

        self.send_button["state"]=tk.DISABLED
        self.set_running(True)
        # 将用户消息显示在主聊天框中（右对齐）
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, f"You: \n{user_message}\n", "user")
        self.chat_display.insert(tk.END, f"{self.model}:\n", "ai")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)  # 滚动到底部

        self.user_input.delete(1.0, tk.END)
        t=Thread(target=self.get_ai_response, args=(user_message,))
        self.threads.append(t)
        t.start()

    def get_ai_response(self, user_message):
        # 调用API获取AI回复的线程
        try:
            for response in self.mode_func(self.session,user_message,model=self.model):
                if not self.is_running():
                    self.chat_display.insert(tk.END, "\n用户已停止", "error")
                    self.chat_display.see(tk.END)
                    self.update()
                    break

                self.chat_display.insert(tk.END, response, "ai_resp")
                self.chat_display.see(tk.END)  # 滚动到底部
            self.chat_display.insert(tk.END, "\n", "ai_resp")
            self.chat_display.see(tk.END)
        except APIRequestError as err:
            print(f"{type(err).__name__}: {err}\n", file=sys.stderr)
        except Exception:
            traceback.print_exc()
        self.send_button["state"]=tk.NORMAL
        self.update_remain()
        with self._lock:
            self.threads.remove(current_thread())

def hdpi_support():
    if sys.platform == 'win32': # Windows下的高DPI支持
        try:
            PROCESS_SYSTEM_DPI_AWARE = 1
            ctypes.OleDLL('shcore').SetProcessDpiAwareness(PROCESS_SYSTEM_DPI_AWARE)
        except (ImportError, AttributeError, OSError):
            pass

if __name__ == "__main__":
    try:
        hdpi_support()
        app = SiderGUI()
        app.mainloop()
    except Exception:
        traceback.print_exc()