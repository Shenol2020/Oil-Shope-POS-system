import os
import webbrowser
import time
import subprocess

project_path = r"C:\Users\USER\Desktop\project\oil-shop-management"

os.chdir(project_path)

subprocess.Popen(["python", "app.py"])

time.sleep(2)

webbrowser.open("http://127.0.0.1:5000")
