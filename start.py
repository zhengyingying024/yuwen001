import os
import sys
import subprocess
import logging
from pathlib import Path
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_base_path():
    """获取基础路径，处理打包后的路径问题"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的可执行文件
        return os.path.dirname(sys.executable)
    else:
        # 如果是直接运行的 Python 脚本
        return os.path.dirname(os.path.abspath(__file__))

def setup_environment():
    """设置环境"""
    base_path = get_base_path()
    logger.info(f"基础路径: {base_path}")
    
    # 设置虚拟环境路径
    if os.name == "nt":  # Windows
        venv_path = os.path.join(base_path, "myenv")
        python_path = os.path.join(venv_path, "Scripts", "python.exe")
        pip_path = os.path.join(venv_path, "Scripts", "pip.exe")
    else:  # Linux/MacOS
        venv_path = os.path.join(base_path, "myenv")
        python_path = os.path.join(venv_path, "bin", "python")
        pip_path = os.path.join(venv_path, "bin", "pip")
    
    # 检查虚拟环境是否存在
    if not os.path.exists(venv_path):
        logger.error(f"虚拟环境不存在: {venv_path}")
        sys.exit(1)
    
    return python_path, pip_path

def install_requirements(pip_path):
    """安装依赖"""
    try:
        requirements_path = os.path.join(get_base_path(), "requirements.txt")
        if not os.path.exists(requirements_path):
            logger.warning(f"requirements.txt 文件不存在: {requirements_path}")
            return
        
        logger.info("开始安装依赖...")
        subprocess.run([pip_path, "install", "-r", requirements_path], check=True)
        logger.info("依赖安装完成")
    except subprocess.CalledProcessError as e:
        logger.error(f"安装依赖时出错: {e}")
        sys.exit(1)

def load_env_vars():
    """加载环境变量"""
    try:
        env_path = os.path.join(get_base_path(), ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)
            logger.info("环境变量加载成功")
        else:
            logger.warning(".env 文件不存在")
    except Exception as e:
        logger.error(f"加载环境变量时出错: {e}")

def run_uvicorn(python_path):
    """运行 uvicorn 服务器"""
    try:
        logger.info("启动 uvicorn 服务器...")
        uvicorn_command = [
            python_path,
            "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", "7860"
        ]
        subprocess.run(uvicorn_command, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"运行 uvicorn 时出错: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"发生未知错误: {e}")
        sys.exit(1)

def main():
    try:
        # 设置环境
        python_path, pip_path = setup_environment()
        
        # 安装依赖
        install_requirements(pip_path)
        
        # 加载环境变量
        load_env_vars()
        
        # 运行 uvicorn 服务器
        run_uvicorn(python_path)
        
    except Exception as e:
        logger.error(f"程序执行出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
    