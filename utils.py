from http.cookies import SimpleCookie

def parse_cookie(cookie):
    cookie_dict = {}
    cookie_jar = SimpleCookie()
    cookie_jar.load(cookie)

    for key, morsel in cookie_jar.items():
        cookie_dict[key] = morsel.value

    return cookie_dict

def to_cookie(cookie_dict):
    cookie_jar = SimpleCookie()
    for key, value in cookie_dict.items():
        cookie_jar[key] = value

    # 返回标准的 Cookie 字符串
    return cookie_jar.output(header='', sep='; ').strip()