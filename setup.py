# setup.py
from setuptools import setup, find_packages

setup(
    name="fpl-chatbot",
    version="1.0.0",
    author="Your Name",
    description="An AI-powered chatbot to help manage your Fantasy Premier League team.",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=[
        "requests",
        "python-dotenv",
    ],
    entry_points={
        "console_scripts": [
            "fpl-chatbot=fpl_chatbot.main:run",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
