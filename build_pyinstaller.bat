@echo off
if exist build (
    rmdir /s /q build
    if exist build echo Error deleting build folder. & exit /B
)
if exist dist (
    rmdir /s /q dist
    if exist dist echo Error deleting dist folder. & exit /B
)
pyinstaller multimodel_chat.py --hidden-import=appdirs --hidden-import=packaging --hidden-import=pyparsing -i res\sider.ico -w
xcopy /e res\* dist\multimodel_chat\res\*