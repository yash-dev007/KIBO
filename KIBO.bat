@echo off
cd /d D:\Projects\KIBO
call "%USERPROFILE%\anaconda3\Scripts\activate.bat" kibo
python main.py
pause