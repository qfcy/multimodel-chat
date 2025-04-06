import sys,os,json,time,threading,functools
from warnings import warn
from urllib.parse import unquote,urlparse
from edgedriver_downloader import download_edgedriver,get_edge_executable
from model_api import SIDER_TOKEN_FILE
from utils import to_cookie
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.common.exceptions import TimeoutException,NoSuchWindowException
import tldextract # 域名提取

TLD_PATH = "res/tld_cache"

def hide_terminal(titles): # 隐藏webdriver的控制台窗口，titles为可能标题的列表
    if sys.platform!="win32":return
    from ctypes import windll,c_char_p
    for title in titles:
        hwnd=windll.user32.FindWindowW(c_char_p(None),title)
        if hwnd!=0:
            windll.user32.ShowWindow(hwnd,0) # 0:SW_HIDE
            break

def async_wrapper(func):
    @functools.wraps(func)
    def inner(*args,**kw):
        t=threading.Thread(target=func,args=args,kwargs=kw)
        t.start()
    return inner

def get_root_domain(url): # 返回根域名（如api.sider.ai变为sider.ai）
    tld = tldextract.TLDExtract(cache_dir=TLD_PATH)
    extracted = tld.extract_str(url)
    return f"{extracted.domain}.{extracted.suffix}"

def cookie_to_json(cookie_list):
    # 将cookie的列表转换为字典
    cookies={}
    for cookie in cookie_list:
        cookie=cookie.copy()
        domain,name=cookie.pop("domain"),cookie.pop("name")
        value=cookie.get("value")
        if value is not None:value = unquote(value)
        if domain in cookies:
            cookies[domain][name] = value
        else:
            cookies[domain]={name: value}
    return cookies

def default_token_getter(driver, cookies): # 用于提取token
    return cookies.get("token")
def deepseek_token_getter(driver, cookies):
    try:
        return driver.execute_script(
                    "return JSON.parse(localStorage.getItem('userToken')).value;")
    except Exception:
        return None

def login_main(driver,url,data_path,token_getter,
               is_running_callback=None,
               done_callback=None,fail_callback=None): # 登录主函数
    if is_running_callback is None:
        is_running_callback=lambda:True # 默认函数

    try:
        driver.set_page_load_timeout(10)
        driver.get(url)
    except TimeoutException:pass
    except Exception as err:
        fail_callback(f"加载网页失败: {err} ({type(err).__name__})")
        return
    while is_running_callback():
        try:
            driver.execute_script( # 隐藏selenium的痕迹
                "try{Object.defineProperty(navigator, 'webdriver', {get: () => undefined});}catch(e){}"
            )
        except NoSuchWindowException:break # 用户已关闭浏览器
        except Exception as err:
            warn("Failed (%s): %s" % (type(err).__name__,str(err))) # 直到主线程退出时，线程才退出

        time.sleep(0.5)
        try:
            if not driver.window_handles:
                break
        except Exception: # 用户已关闭浏览器
            break

        cookie_list = driver.get_cookies() or [] # 每隔一段时间自动保存cookie
        all_cookies = cookie_to_json(cookie_list)
        try:
            cookies = all_cookies[f".{get_root_domain(url)}"]
        except KeyError:
            cookies = all_cookies[urlparse(url).netloc]

        token = token_getter(driver, cookies) # 规定回调函数token_getter返回token的值，或None
        if token is not None:
            if token.lower().startswith("bearer"):
                token=token[6:].strip() # 去掉开头的bearer
            cookie_data=to_cookie(cookies)
            try:
                with open(data_path,encoding="utf-8") as f:
                    data=json.load(f) # 加载旧的数据
            except (OSError, ValueError):
                data = {}
            data["token"] = token # 更新数据
            data["cookie"] = cookie_data
            with open(data_path,"w",encoding="utf-8") as f:
                json.dump(data,f)

            if done_callback:done_callback()
            return
    fail_callback("未检测到cookie，请重新登录!")

DRIVER_PATH="driver"
def login(url,data_path,token_getter,is_running_callback=None,
          done_callback=None,fail_callback=None):
    driver_executable=os.path.join(DRIVER_PATH,"msedgedriver.exe")
    if not os.path.isfile(driver_executable):
        download_edgedriver() # 自动下载edgedriver

    service = Service(executable_path=driver_executable)
    driver = webdriver.Edge(service=service)
    hide_terminal([get_edge_executable(),
                   os.path.realpath(driver_executable)])

    login_main(driver,url,data_path,token_getter,is_running_callback,
           async_wrapper(done_callback),async_wrapper(fail_callback))
    try:driver.quit()
    except Exception:pass