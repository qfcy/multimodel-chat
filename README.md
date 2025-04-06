**The English introduction is shown below the Chinese version.**

一个多合一的AI聊天工具，将ChatGPT、Gemini、LLaMA，以及DeepSeek、讯飞星火、通义千问、kimi等大模型的API集成在同一个界面中，简化了AI工具的使用，支持多模型对比聊天功能。

## 运行

下载源代码后，切换到本仓库的根目录，输入以下命令，即可：
```
pip install -r requirements.txt
python multimodel_chat.py
```

## 效果图

![](https://i-blog.csdnimg.cn/direct/007cfc6d11944673b9021050021f8d48.png)

## 实现细节

工具通过[sider.ai](sider.ai)提供了对ChatGPT、Claude、Gemini等国外模型的访问，支持账号管理，以及手动登录和输入API Key的功能。  
工具中的[deepseek_hash.py](deepseek_hash.py)实现了处理DeepSeek网页端的PoW验证，并爬取DeepSeek网页端聊天（网页端聊天可能会遇到“服务器繁忙”，但是无需申请付费的DeepSeek API）。  
此外，在用户登录页面，工具支持自动下载`selenium`库所需的edgedriver并解压，无需手动配置edgedriver环境。  

---

An all-in-one AI chat tool that integrates APIs of multiple large models, including ChatGPT, Gemini, LLaMA, DeepSeek, iFlytek Spark, Tongyi Qianwen, Kimi, and more, into a single interface. It simplifies the use of AI tools and supports multi-model comparative chat functionality.

## Run

After downloading the source code, navigate to the root directory of this repository and enter the following commands:

```
pip install -r requirements.txt
python multimodel_chat.py
```

## Screenshot

![](https://i-blog.csdnimg.cn/direct/007cfc6d11944673b9021050021f8d48.png)

## Implementation Details

The tool provides access to foreign models such as ChatGPT, Claude, and Gemini via [sider.ai](sider.ai). It also supports account management, manual login, and API Key input functionality.  
The [deepseek_hash.py](deepseek_hash.py) script handles the PoW verification for DeepSeek's web client and enables web-based chat scraping (note: web-based chat may encounter "server busy" issues but does not require a paid DeepSeek API subscription).  
Additionally, on the user login page, the tool supports automatic downloading and extraction of the `selenium` library's required `edgedriver`, eliminating the need for manual configuration of the edgedriver environment.
