import os
import subprocess
from dotenv import load_dotenv

# 激活虚拟环境（不同操作系统不同激活方式）
def activate_virtualenv():
    if os.name == "nt":  # Windows
        activate_script = os.path.join(os.getcwd(), "myenv", "Scripts", "activate.bat")
        subprocess.run([activate_script], shell=True)
    else:  # Linux/MacOS
        activate_script = os.path.join(os.getcwd(), "myenv", "bin", "activate")
        subprocess.run(f"source {activate_script}", shell=True, executable="/bin/bash")

# 安装 requirements.txt 中的依赖
def install_requirements():
    try:
        subprocess.run([os.path.join("myenv", "Scripts", "pip") if os.name == "nt" else os.path.join("myenv", "bin", "pip"),
                        "install", "-r", "requirements.txt"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"安装依赖时出错: {e}")

# 加载环境变量
def load_env_vars():
    load_dotenv()

# 运行 uvicorn 服务器
def run_uvicorn():
    try:
        uvicorn_command = [os.path.join("myenv", "Scripts", "uvicorn") if os.name == "nt" else os.path.join("myenv", "bin", "uvicorn"),
                           "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
        subprocess.run(uvicorn_command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"运行 uvicorn 时出错: {e}")
    except FileNotFoundError:
        print("未找到 uvicorn，请确保已经安装。")

if __name__ == "__main__":
    # 激活虚拟环境
    activate_virtualenv()
    # 安装依赖
    install_requirements()
    # 加载环境变量
    load_env_vars()
    # 运行 uvicorn 服务器
    run_uvicorn()
    