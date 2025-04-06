import struct
import wasmtime

WASM_PATH = "res/sha3_wasm_bg.wasm" # 可从chat.deepseek.com/static/sha3_wasm_bg.7b9ca65ddd.wasm获得

class DeepSeekHash:
    def __init__(self, filename):
        engine = wasmtime.Engine()
        self.store = wasmtime.Store(engine)
        with open(filename, 'rb') as f:
            module = wasmtime.Module(engine, f.read())
        self.instance = wasmtime.Instance(self.store, module, [])
        self.offset = 0 # 当前内存地址

        self.memory = self.instance.exports(self.store)["memory"]
    def encodeString(self,text,alloc,realloc):
        data = text.encode("utf-8")
        ptr = alloc(self.store, len(data), 1)
        self.memory.write(self.store, data, ptr)
        self.offset = len(data)
        return ptr
    def calculate_hash(self, challenge, salt, difficulty, expire_at):
        # 获取函数
        wasm_solve = self.instance.exports(self.store)["wasm_solve"]
        __wbindgen_export_0 = self.instance.exports(self.store)["__wbindgen_export_0"]
        __wbindgen_export_1 = self.instance.exports(self.store)["__wbindgen_export_1"]
        __wbindgen_add_to_stack_pointer = self.instance.exports(self.store)[
                                            "__wbindgen_add_to_stack_pointer"]

        prefix = f"{salt}_{expire_at}_"
        try:
            retptr = __wbindgen_add_to_stack_pointer(self.store, -16)
            ptr0 = self.encodeString(
                challenge,
                __wbindgen_export_0,__wbindgen_export_1
            )
            len0 = self.offset
            ptr1 = self.encodeString(
                prefix,
                __wbindgen_export_0,__wbindgen_export_1
            )
            len1 = self.offset

            wasm_solve(self.store, retptr, ptr0, len0, ptr1, len1, difficulty)

            # 读取返回的状态和值
            data = self.memory.read(self.store, retptr, retptr + 4)
            status = struct.unpack("<i", data)[0]
            value = struct.unpack("<d", self.memory.read(self.store, retptr + 8, retptr + 16))[0]

            if status == 0:return None
            return value
        finally:
            __wbindgen_add_to_stack_pointer(self.store, 16)

def calculate_hash(challenge, salt, difficulty, expire_at):
    hasher = DeepSeekHash(WASM_PATH)
    return hasher.calculate_hash(challenge, salt, difficulty, expire_at)

if __name__ == "__main__":
    result = calculate_hash("3471d7bba7beac588a60de623cb6fa723409f9ac0f01637c034070f3ccf18e89", "14f3db8f4450498d2e7c", 144000.0, 1741780541739)
    print(f"Hash Result: {result}")