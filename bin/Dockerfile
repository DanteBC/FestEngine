FROM python:3.9-slim-bullseye

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y \
        gettext \
        vlc \
        libjpeg-dev \
        zlib1g-dev \
        libgtk-3-dev \
        pkg-config \
        build-essential && \
    python3 -m pip install -U pip setuptools wheel && \
    python3 -m pip install -U typing-extensions six && \
    python3 -m pip install -U \
        -f https://extras.wxpython.org/wxPython4/extras/linux/gtk3/debian-11 \
        --no-cache-dir \
        wxPython && \
    python3 -m pip install -U pyinstaller python-vlc

WORKDIR /app
COPY . .
WORKDIR /app/bin
RUN python3 ./build.py -novlc && \
    mv ./install.sh ./FestEngine/ && \
    mkdir -p ./FestEngine/locale/ru/LC_MESSAGES && \
    msgfmt -o ./FestEngine/locale/ru/LC_MESSAGES/main.mo \
           ../src/locale/ru/LC_MESSAGES/main.po
RUN tar -zcvf fest_engine.tar.gz FestEngine