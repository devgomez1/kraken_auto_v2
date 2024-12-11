from setuptools import setup, find_packages

setup(
    name="kraken_auto",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'ccxt>=4.0.0',
        'pandas>=2.0.0',
        'pyyaml>=6.0.0',
        'python-dotenv>=1.0.0',
        'pytest>=7.0.0',
        'pytest-asyncio>=0.21.0'
    ]
)