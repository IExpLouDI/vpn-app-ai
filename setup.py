from setuptools import find_packages, setup

setup(
    name="pyvpn",
    version="0.1.0",
    packages=find_packages(where="src"),
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
