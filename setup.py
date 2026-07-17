from setuptools import find_packages, setup

TOP_LEVEL_MODULES = [
    "app",
    "cli",
    "config",
    "server",
    "client",
    "routing",
    "tun",
    "tun_windows",
    "status",
    "privileges",
]

setup(
    name="pyvpn",
    version="0.1.0",
    packages=find_packages(where="src"),
    py_modules=TOP_LEVEL_MODULES,
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "cryptography",
        "lz4",
    ],
    entry_points={
        "console_scripts": [
            "pyvpn=app:main",
        ],
    },
)
