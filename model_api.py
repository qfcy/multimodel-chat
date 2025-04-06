# 访问AI API的库，基于sider-ai-api项目修改
import sys,os,json,traceback,pprint,base64
import gzip,bz2,zlib
from warnings import warn
from urllib.parse import unquote
import requests
try:import brotli # 处理brotli压缩格式
except ImportError:brotli=None
try:import openai
except ImportError:openai=None
from utils import parse_cookie
from deepseek_hash import calculate_hash

SIDER_ORIGIN="chrome-extension://dhoenijjpgpeimemopealfcbiecgceod"
TIMEZONE="Asia/Shanghai"
SIDER_APPNAME="ChitChat_Edge_Ext"
SIDER_APPVERSION="4.40.0"
DEEPSEEK_ORIGIN="https://chat.deepseek.com"
DEEPSEEK_URL_PATH="/api/v0/chat/completion"
DEEPSEEK_ALGORITHMS=["DeepSeekHashV1"]

SIDER_TOKEN_FILE="_sider_token.json"
OPENAI_TOKEN_FILE="_openai_token.json"
DEEPSEEK_TOKEN_FILE="_deepseek_token.json"
SIDER_COOKIE_TEMPLATE='token=Bearer%20{token}; '
'refresh_token=discard; '
'userinfo-avatar=https://chitchat-avatar.s3.amazonaws.com/default-avatar-14.png; '
'userinfo-name=User; userinfo-type=phone; '

HEADER={ # 从浏览器的开发工具复制获得
 'Accept': '*/*',
 'Accept-Encoding': 'gzip, deflate, br, zstd',
 'Accept-Language': 'zh-CN,zh;q=0.9,en,en-US;q=0.8,en-GB;q=0.7,ja;q=0.6',
 'Cache-Control': 'no-cache',
 'Pragma': 'no-cache',
 'Sec-Fetch-Dest': 'empty',
 'Sec-Fetch-Mode': 'cors',
 'Sec-Fetch-Site': 'none',
 'sec-ch-ua': '"Chromium";v="133", "Microsoft Edge";v="133", "Not?A_Brand";v="99"',
 'sec-ch-ua-mobile': '?0',
 'sec-ch-ua-platform': '"Windows"',
 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 '
               'Edg/133.0.0.0'
}
DEEPSEEK_EXTRA_HEADER={
"x-app-version":"20241129.1",
"x-client-locale":"zh_CN",
"x-client-platform":"web",
"x-client-version":"1.0.0-always"
}

SIDER_MODELS=[#"sider", # Sider Fusion
    "gpt-4o-mini",
    #"claude-3-haiku",
    "claude-3.5-haiku",
    #"gemini-1.5-flash",
    "gemini-2.0-flash",
    #"llama-3", # llama 3.1 70B
    "llama-3.3-70b",
    #"deepseek-chat", # deepseek-v3
    #"deepseek-r1-distill-llama-70b" # deepseek r1 70B
]
SIDER_ADVANCED_MODELS=["gpt-4o",
"claude-3.7-sonnet",
"gemini-2.0-pro",
"llama-3.1-405b",
"o1-mini",
"o1", # o1
"gpt-4.5",
#"deepseek-reasoner" # deepseek-r1
]
DEEPSEEK_MODELS=["DeepSeek V3 (网页版)","DeepSeek R1 (网页版)"]

class NeedToolCall(Exception):
    def __init__(self,tool_calls):
        self.tool_calls = tool_calls
    def __str__(self):
        return f"Unhandled tool call from AI: {self.tool_calls}"

class APIRequestError(Exception):pass
class SiderAPIRequestError(APIRequestError):pass
class DeepSeekAPIRequestError(APIRequestError):pass

def del_key(dct, keys):
    for key in keys:
        if key in dct:
            del dct[key]

def normpath(path):
    # 重写os.path.normpath。规范化Windows路径，如去除两端的双引号等
    path=os.path.normpath(path).strip('"')
    if path.endswith(':'): # 如果路径是盘符，如 C:
        path += '\\'
    return path

def convert_to_dict(obj,module):
    # 将openai的返回结果转换为字典
    if isinstance(obj,list) or isinstance(obj,tuple):
        type_=type(obj)
        obj=type_(convert_to_dict(sub,module) for sub in obj)
    if getattr(type(obj),"__module__","").startswith(module):
        obj=dict(obj)
        for key in obj.keys():
            obj[key]=convert_to_dict(obj[key],module)
    return obj

def upload_image(filename,header):
    url="https://api1.sider.ai/api/v1/imagechat/upload"
    header = header.copy()
    #header["content-type"] = "multipart/form-data"
    #header["accept-encoding"] = "gzip, deflate"
    with open(filename, 'rb') as img:
        files = {'file': ("ocr.jpg",img,'application/octet-stream')}  # file 应与API要求的字段名一致
        response = requests.post(url, headers=header, files=files)
        if response.status_code!=200:
            # respose.text可能过长 (如果遇到了Cloudflare验证等)，因此截取前1024个字符
            raise Exception({"error": response.status_code, "message": response.text[:1024]})
    coding=response.headers.get('Content-Encoding')
    if not response.content.startswith(b"{") and coding is not None:
        decompress=None
        if coding == 'deflate':
            decompress=zlib.decompress
        elif coding == 'gzip':decompress=gzip.decompress
        elif coding == 'bzip2':decompress=bz2.decompress
        elif brotli is not None and coding == 'br':
            decompress=brotli.decompress
        data=decompress(response.content)
    else:
        data=response.content
    return json.loads(data.decode("utf-8"))

class BaseSession:
    def __init__(self,*args,**kw):pass
    def chat(self,prompt,model=None,stream=True):pass

class SiderSession(BaseSession):
    def __init__(self,token=None,context_id="",cookie=None,update_info_at_init=True,
                 config_file=SIDER_TOKEN_FILE,extra_headers=None):
        if token is None:
            if cookie is None:
                # 尝试读取配置文件
                if not os.path.isfile(config_file):
                    raise OSError(f"{config_file} is required since neither token nor cookie is provided")
                with open(config_file,encoding="utf-8") as f:
                    config=json.load(f)
                    token=config.get("token")
                    cookie=config.get("cookie")
                    extra_headers=config.get("extra_headers")
                if token is None and cookie is None:
                    raise ValueError(f"Neither token nor cookie is provided in {config_file}")
        if token is None:
            token=parse_cookie(cookie).get("token")
            if token is None:
                raise ValueError("token is not provided in cookie")
            if token.startswith("Bearer "):
                token=token[7:] # token不包含头部的Bearer

        self.context_id=context_id
        self.total=self.remain=None # 总/剩下调用次数
        self.advanced_total=self.advanced_remain=None # 高级模型的调用次数
        self.token=token

        self.header=HEADER.copy()
        if extra_headers:self.header.update(extra_headers)
        self.header['Origin']=SIDER_ORIGIN
        self.header['authorization']=f'Bearer {token}'
        if cookie is None:
            cookie=SIDER_COOKIE_TEMPLATE.format(token=token)
        self.header['Cookie']=cookie
        if update_info_at_init:
            try:self.update_userinfo()
            except Exception as err:
                warn(f"Failed to get user info ({type(err).__name__}): {err}")
    def update_userinfo(self):
        url="https://api3.sider.ai/api/v1/completion/limit/user"
        params = {
            "app_name": SIDER_APPNAME,
            "app_version": SIDER_APPVERSION,
            "tz_name": TIMEZONE
        }
        response = requests.get(url, params=params, headers=self.header)
        response.raise_for_status()
        data = response.json()
        self.total=data["data"]["basic_credit"]["count"] or self.total
        self.remain=data["data"]["basic_credit"]["remain"] or self.remain
        self.advanced_total=data["data"]["advanced_credit"]["count"] or self.advanced_total
        self.advanced_remain=data["data"]["advanced_credit"]["remain"] or self.advanced_remain
    def get_text(self,url,header,payload,deep_search=False):
        # 一个生成器，获取输出结果
        resp = requests.post(url, headers=header, json=payload, stream=True)
        resp.raise_for_status()
        for line_raw in resp.iter_lines():
            if not line_raw.strip():continue
            try:
                # 解析每一行的数据
                line = line_raw.decode("utf-8")
                if payload.get("stream",True):
                    if not line.startswith("data:"):continue
                    response = line[5:]  # 去掉前缀 "data:"
                else:
                    response = line

                if not response:continue # 确保数据非空
                if response=="[DONE]":break
                data = json.loads(response)

                if data["msg"].strip():
                    #yield "<Message: %s Code: %d>" % (data["msg"],data["code"])
                    raise SiderAPIRequestError("<Message: %s Code: %d>" % (data["msg"],data["code"]))
                if data["data"] is None:continue
                if "text" in data["data"]:
                    self.context_id=data["data"].get("cid","") or self.context_id # 对话上下文
                    if payload.get("model") in SIDER_ADVANCED_MODELS:
                        self.advanced_total=data["data"].get("total",None) or self.advanced_total
                        self.advanced_remain=data["data"].get("remain",None) or self.advanced_remain
                    else:
                        self.total=data["data"].get("total",None) or self.total # or: 保留旧的self.total
                        self.remain=data["data"].get("remain",None) or self.remain
                    yield data["data"]["text"] # 返回文本响应

                if deep_search and "deep_search" in data["data"]:
                    search=data["data"]["deep_search"]
                    if search["status"]=="answering":
                        yield search["field"].get("answer_fragment","")
                    elif "field" in search:
                        field=str(search['field'])
                        if len(field)>=128:field=pprint.pformat(search['field'])
                        yield f"<Status: {search['status']}: {field}>\n"
                    else:
                        yield f"<Status: {search['status']}>\n"
            except APIRequestError:raise
            except Exception as err:
                warn(f"Error processing stream ({type(err).__name__}): {err} Raw: {line_raw}")
    def chat(self,prompt,model="gpt-4o-mini",
             stream=True,output_lang=None,thinking_mode=False,
             data_analysis=True,search=True,
             text_to_image=False,artifact=True):
        # 使用提示词调用AI，返回结果的字符串生成器(如果参数stream为True，默认)
        # 或结果字符串(如果stream为False)
        auto_tools=[]
        if data_analysis:auto_tools.append("data_analysis")
        if search:auto_tools.append("search")
        if text_to_image:auto_tools.append("artifact")

        url = "https://sider.ai/api/v3/completion/text"
        header = self.header.copy()
        header["content-type"] = 'application/json'
        payload = {
            "prompt": prompt,
            "stream": stream,
            "app_name": SIDER_APPNAME,
            "app_version": SIDER_APPVERSION,
            "tz_name": TIMEZONE,
            "cid": self.context_id, # 对话上下文id，如果为空则开始新对话
            "model": model,
            "search": False,
            "auto_search": False,
            "filter_search_history": False,
            "from": "chat",
            "group_id": "default",
            "chat_models": [],
            "files": [],
            "prompt_templates": [],
            "tools": {"auto": auto_tools},
            "extra_info": {
                "origin_url": SIDER_ORIGIN+"/standalone.html",
                "origin_title": "Sider"
            }
        }
        if artifact: # 在artifact的新窗口中显示结果
            payload["prompt_templates"].append(
                {"key":"artifacts", "attributes": {"lang": "original"}}
            )
        if thinking_mode:
            payload["prompt_templates"].append(
                {"key": "thinking_mode", "attributes": {}}
            )
        if output_lang is not None: # 模型输出语言，如"en","zh-CN"
            payload["output_language"]=output_lang

        return self.get_text(url,header,payload)
    def ocr(self,filename,model="gemini-2.0-flash",stream=True):
        # 一个生成器，调用OCR并返回结果
        data = upload_image(filename,self.header)
        img_id = data["data"]["id"]
        url="https://api2.sider.ai/api/v2/completion/text"
        payload = {
            "prompt": "ocr",
            "stream": stream,
            "app_name": SIDER_APPNAME,
            "app_version": SIDER_APPVERSION,
            "tz_name": TIMEZONE,
            "cid": self.context_id,
            "model": model,
            "from": "ocr",
            "image_id": img_id,
            "ocr_option": {
                "force_ocr": True,
                "use_azure": False
            },
            "tools": {},
            "extra_info": {
                "origin_url": SIDER_ORIGIN+"/standalone.html",
                "origin_title": "Sider"
            }
        }
        return self.get_text(url,self.header,payload)
    def translate(self,content,target_lang="Chinese (Simplified)",model="gpt-4o-mini",stream=True):
        url="https://api3.sider.ai/api/v2/completion/text"
        payload = {
            "prompt": "",
            "stream": stream,
            "app_name": SIDER_APPNAME,
            "app_version": SIDER_APPVERSION,
            "tz_name": TIMEZONE,
            "model": model,
            "from": "translate",
            "prompt_template": {
                "key": "translate-basic",
                "attributes": {
                    "input": content,
                    "target_lang": target_lang # 目标语言名称，如"English"或"Chinese (Simplified)"
                }
            },
            "tools": {
                "force": "reader"
            },
            "extra_info": {
                "origin_url": SIDER_ORIGIN+"/standalone.html",
                "origin_title": "Sider"
            }
        }
        return self.get_text(url,self.header,payload)
    def search(self,content,model="gpt-4o-mini",stream=True,focus=None):
        # focus为字符串列表，包含搜索网站的域名，如"wikipedia.org"或"youtube.com"等
        url="https://api3.sider.ai/api/v2/completion/text"
        payload = {
            "prompt": content,
            "stream": stream,
            "app_name": SIDER_APPNAME,
            "app_version": SIDER_APPVERSION,
            "tz_name": TIMEZONE,
            "model": model,
            "from": "deepsearch",
            "deep_search": {
                "enable": True
            },
            "tools": {},
            "extra_info": {
                "origin_url": SIDER_ORIGIN+"/standalone.html",
                "origin_title": "Sider"
            }
        }
        if focus:
            payload["deep_search"]["focus"]=focus
        return self.get_text(url,self.header,payload,deep_search=True)
    def improve_grammar(self,content,model="gpt-4o-mini",stream=True):
        url="https://api3.sider.ai/api/v1/completion/improve_writing"
        payload = {"content":content,
                   "model":model,
                   "tz_name":TIMEZONE,
                   "app_name":SIDER_APPNAME,
                   "app_version":SIDER_APPVERSION,
                   "stream": stream}
        return self.get_text(url,self.header,payload)

class OpenAISession(BaseSession): # openai风格接口，用于kimi、deepseek API、星火等
    def __init__(self, config_file=OPENAI_TOKEN_FILE):
        self.models={}
        self.reset_config(config_file)
        self.history = []  # 用于保存对话上下文
        self.message_id=None
    def reset_config(self, config_file=OPENAI_TOKEN_FILE):
        # 重新加载自身的配置
        self.models={}
        with open(config_file,encoding="utf-8") as f:
            config=json.load(f)
            for model in config:
                name=model.pop("name")
                self.models[name]=model

    def openai_handler(self, prompt, model, stream=True): # 创建流，返回create_stream闭包函数
        kw=self.models[model].copy()
        base_url=kw.pop("base_url")
        api_key=kw.pop("api_key")
        del_key(kw,["user_friendly_name","use_openai"]) # 删除不用于API请求的项
        # 调用 OpenAI API
        client=openai.OpenAI(base_url=base_url,api_key=api_key)
        def create_stream(): # create_stream返回一个字典生成器，返回AI的原始响应
            response = client.chat.completions.create(
                            model=model,  # 选择模型
                            messages=self.history,
                            stream=True,
                            **kw,
                        )
            for data in response: # pylint: disable=not-an-iterable
                yield convert_to_dict(data,"openai")
        return create_stream
    def no_openai_handler(self,prompt,model,stream=True): # 使用requests库创建流
        kw=self.models[model].copy()
        base_url=kw.pop("base_url")
        api_key=kw.pop("api_key")
        del_key(kw,["user_friendly_name","use_openai"])
        headers = {} # HEADER.copy()
        headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })
        payload = {
            "model": model,
            "messages": self.history,
            "stream": stream,
            **kw,
        }
        def create_stream():
            response = requests.post(base_url, headers=headers, json=payload)
            return self.resp_parser(response)
        return create_stream
    def resp_parser(self,resp):
        for line_raw in resp.iter_lines():
            if not line_raw.strip():continue
            try:
                # 解析每一行的数据
                line = line_raw.decode("utf-8")
                if not line.startswith("data:"):
                    try:
                        err_data=json.loads(line)
                        raise APIRequestError(
                    f"""error in API call: {err_data.get('msg',err_data.get('message','Unknown message'))} \
({err_data.get('code','Unknown error code')}) raw: {line_raw}""")
                    except ValueError:pass # 不是json
                response = line[5:].strip()  # 去掉前缀 "data:"

                if not response:continue # 确保数据非空
                if response=="[DONE]":break
                data = json.loads(response)
                yield data
            except APIRequestError:raise
            except Exception as err:
                warn(f"Error processing stream ({type(err).__name__}): {err} Raw: {line_raw}")
    def get_text(self,dict_stream):
        # 将字典响应转换为文本回复 (需要工具调用时抛出NeedToolCall)
        tool_calls=[]
        for chunk in dict_stream:
            if chunk.get("code",0)!=0:
                raise APIRequestError(
                f"error in response: {chunk.get('message','Unknown message')} ({chunk['code']}) raw: {chunk!r}")
            if "message_id" in chunk:
                self.message_id=chunk["message_id"]
            if "choices" in chunk and chunk["choices"]:
                choice = chunk["choices"][0]
                if "delta" in choice:
                    for tool_call in (choice["delta"].get("tool_calls") or []):
                        if tool_call["function"]["arguments"] and tool_call["id"] is None:
                            tool_calls[-1]["function"]["arguments"] = tool_call["function"]["arguments"]  # 在流中组合多个tool_call
                        else:
                            tool_calls.append(tool_call)
                    if choice.get("finish_reason") == "tool_calls":
                        raise NeedToolCall(tool_calls)  # NeedToolCall 必须被调用者处理
                    elif choice["delta"].get("type")=="search_index": # deepseek的搜索引用索引
                        for cite in choice["delta"].get("search_indexes",[]):
                            print(f"[参考资料 {cite['cite_index']}: {cite['url']}]")
                    else:
                        fragment = choice["delta"].get("content") or ""
                        if fragment:yield fragment  # 逐步输出生成的内容

    def chat(self, prompt, model, stream=True):
        self.add_to_history(prompt=prompt)
        use_openai = self.models[model].get("use_openai",True) # 获取是否需要通过openai库调用
        if use_openai and openai is None:
            raise NotImplementedError("openai library is required")
        handler = self.openai_handler if use_openai else self.no_openai_handler
        create_stream = handler(prompt, model, stream)
        if stream:
            flag=True
            while flag: # 调用工具的循环
                flag=False
                response = create_stream()
                # 如果是流式返回，返回生成器
                full_response = ""
                try:
                    gen = self.get_text(response)
                    for fragment in gen:
                        yield fragment
                        full_response += fragment  # 收集完整响应
                except NeedToolCall as err:
                    tool_calls=err.tool_calls
                    flag=True
                    self.history.append({"role": "assistant","function_call":None,
                                         "tool_calls":tool_calls,"content":"[TOOL_CALL]"})
                    for tool_call in tool_calls:
                        print(f"{model}正在查询工具: {tool_call['function']['name']} ({tool_call['id']})")
                        self.history.append({
                            "role": "tool",
                            "tool_call_id": tool_call['id'],
                            "name": tool_call['function']['name'],
                            "content": tool_call['function']['arguments'],  # 提交工具调用结果 (这里直接提交原始参数)
                        })

                if not flag:
                    self.add_to_history(response=full_response)
        else:
            # 如果不是流式返回，直接返回最终结果
            response = list(create_stream())[0]
            full_content = response["choices"][0]["message"]["content"]
            self.add_to_history(response=full_content)
            yield full_content
    def add_to_history(self,prompt=None,response=None):
        if prompt is not None:self.history.append({"role": "user", "content": prompt})
        if response is not None:self.history.append({"role": "assistant", "content": response})

class DeepSeekSession(OpenAISession): # TODO: 修复PoW认证
    def __init__(self,token=None,cookie=None,
                 config_file=DEEPSEEK_TOKEN_FILE,extra_headers=None):
        if token is None and cookie is None:
            # 尝试读取配置文件
            if not os.path.isfile(config_file):
                raise OSError(f"{config_file} is required since neither token nor cookie is provided")
            with open(config_file,encoding="utf-8") as f:
                config=json.load(f)
                token=config.get("token")
                cookie=config.get("cookie")
                extra_headers=config.get("extra_headers")
            if token is None or cookie is None:
                raise ValueError(f"token or cookie is not provided in {config_file}")

        if token is None or cookie is None:
            raise ValueError(f"either token or cookie is not provided")

        self.context_id=None
        self.message_id=None # 父消息id (请求中允许为None)
        self.token=token

        self.header=HEADER.copy()
        self.header.update(DEEPSEEK_EXTRA_HEADER)
        if extra_headers:self.header.update(extra_headers)
        self.header['Origin']=DEEPSEEK_ORIGIN
        self.header['authorization']=f'Bearer {token}'
        self.header['Cookie']=cookie
    def create_session(self):
        url="https://chat.deepseek.com/api/v0/chat_session/create"
        payload={"character_id": None}
        resp = requests.post(url, headers=self.header, json=payload)
        resp.raise_for_status()
        result=resp.json()
        try:
            code=result["data"]["biz_code"]
            if code != 0:
                warn(f"Create new DeepSeek session failed: {result['data']['biz_msg']} ({code})")
            self.context_id=result["data"]["biz_data"]["id"]
        except Exception as err:
            warn(f"Failed to parse DeepSeek session info: {err} ({type(err).__name__})")
    def new_pow_challenge(self):
        url = "https://chat.deepseek.com/api/v0/chat/create_pow_challenge"
        payload = {"target_path": DEEPSEEK_URL_PATH}
        resp = requests.post(url, headers=self.header, json=payload)
        resp.raise_for_status()
        result=resp.json()
        if result["code"] != 0:
            raise DeepSeekAPIRequestError(
                f"Failed to get new PoW challenge: {result['msg']} ({result['code']})")
        challenge = result["data"]["biz_data"]["challenge"]
        return challenge
    def solve_pow(self):
        challenge = self.new_pow_challenge()
        result = challenge.copy()
        del result["expire_at"]
        del result["expire_after"]
        del result["target_path"]
        challenge["difficulty"]=float(challenge["difficulty"])
        if challenge["algorithm"] not in DEEPSEEK_ALGORITHMS:
            raise DeepSeekAPIRequestError(f"Unsupported algorithm: {challenge['algorithm']}")

        result["answer"] = int(calculate_hash(challenge["challenge"],
                               challenge["salt"],challenge["difficulty"],
                               challenge["expire_at"])) # answer!
        return result
    def chat(self,prompt,model="DeepSeek V3 (网页版)",
             stream=True,search=True,thinking_mode=False): # TODO: 目前不支持stream为False
        if "reasoner" in model.lower() or "r1" in model.lower():
            thinking_mode=True

        if self.context_id is None:
            self.create_session()
        url = f"https://chat.deepseek.com{DEEPSEEK_URL_PATH}"
        header = self.header.copy()
        pow_result = self.solve_pow()
        header["x-ds-pow-response"] = base64.b64encode(json.dumps(pow_result).encode("utf-8"))
        payload = {
            "chat_session_id": self.context_id,
            "parent_message_id": self.message_id,
            "prompt": prompt,
            "ref_file_ids": [],
            "search_enabled": search,
            "thinking_enabled": thinking_mode,
        }
        print("<等待DeepSeek回答中 ...>")
        resp = requests.post(url, headers=header, json=payload, stream=True)
        resp.raise_for_status()
        return self.get_text(self.resp_parser(resp))


class Session(SiderSession): # 组合sider接口和openai,deepseek接口 (以sider为主)
    def __init__(self,openai_config=OPENAI_TOKEN_FILE,
                 deepseek_config=DEEPSEEK_TOKEN_FILE,**kw):
        self.sider=SiderSession(**kw)
        self.openai=OpenAISession(config_file=openai_config)
        self.deepseek=DeepSeekSession(config_file=deepseek_config)
        self.to_sider=[]
        self.to_deepseek=[]
    def chat(self,prompt,model,stream=True,**kw):
        # 同步openai和sider,deepseek之间的历史记录，公共历史记录维护在self.openai
        if model.lower().endswith("(sider)"):
            # 调用sider
            model=model[:-7].strip() # 去掉末尾的"(sider)"子串
            if self.to_sider:
                prompt=f"Additional history: {self.to_sider}\nPrompt: {prompt}"
                self.to_sider.clear()
            response=""
            for fragment in self.sider.chat(prompt,model,stream,**kw):
                yield fragment
                response+=fragment
            self.openai.add_to_history(prompt,response)
            self.to_deepseek.append(self.openai.history[-2:])

        elif model in DEEPSEEK_MODELS:
            if self.to_deepseek:
                prompt=f"Additional history: {self.to_deepseek}\nPrompt: {prompt}"
                self.to_deepseek.clear()
            response=""
            for fragment in self.deepseek.chat(prompt,model,stream,**kw):
                yield fragment
                response+=fragment
            self.openai.add_to_history(prompt,response)
            self.to_sider.append(self.openai.history[-2:])

        else:
            orig_len=len(self.openai.history)
            for fragment in self.openai.chat(prompt,model,stream): # 忽略其他参数kw
                yield fragment
            self.to_sider.append(
                self.openai.history[-(len(self.openai.history)-orig_len):])
            self.to_deepseek.append(
                self.openai.history[-(len(self.openai.history)-orig_len):])
    def ocr(self,filename,model="gemini-2.0-flash (sider)",stream=True):
        if model.lower().endswith("(sider)"):
            # 调用sider
            model=model[:-7].strip() # 转换为sider的模型名称
            return super().ocr(filename,model,stream)
        else:
            raise NotImplementedError("OCR is unsupported without Sider models")
    def translate(self,content,target_lang="Chinese (Simplified)",model="gpt-4o-mini (sider)",
                  stream=True):
        if model.lower().endswith("(sider)"):
            model=model[:-7].strip()
            return super().translate(content,target_lang,model,stream)
        else:
            prompt=f"Translate to {target_lang} and don't output any extra info:\n{content}"
            return self.chat(prompt,model,stream)
    def search(self,content,model="gpt-4o-mini (sider)",stream=True,focus=None):
        if model.lower().endswith("(sider)"):
            model=model[:-7].strip()
            return super().search(content,model,stream,focus)
        else:
            raise NotImplementedError("Search is unsupported without Sider models")
    def improve_grammar(self,content,model="gpt-4o-mini",stream=True):
        if model.lower().endswith("(sider)"):
            model=model[:-7].strip()
            return super().improve_grammar(content,model)
        else:
            prompt=f"Improve the grammar of this text:\n{content}"
            return self.chat(prompt,model,stream)
    def __getattr__(self,attr): # 兼容旧的SiderSession
        return getattr(self.sider,attr)