FROM python:3.8-slim-bullseye

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
    pip install -U pip setuptools wheel && \
    pip install -U \
        --no-cache-dir \
        -f https://extras.wxpython.org/wxPython4/extras/linux/gtk3/debian-11 \
        wxPython && \
    pip install -U pyinstaller python-vlc

WORKDIR /app
COPY . .
WORKDIR /app/bin
RUN python3 ./build.py -novlc && \
    mv ./install.sh ./FestEngine/ && \
    mkdir -p ./FestEngine/locale/ru/LC_MESSAGES && \
    msgfmt -o ./FestEngine/locale/ru/LC_MESSAGES/main.mo \
           ../src/locale/ru/LC_MESSAGES/main.po
RUN tar -zcvf fest_engine.tar.gz FestEngine