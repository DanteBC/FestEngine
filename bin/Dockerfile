FROM debian:11

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y \
        gettext \
        python3 \
        python3-pip \
        vlc \
        libjpeg-dev \
        zlib1g-dev \
        libgtk-3-dev \
        pkg-config \
        libgl1-mesa-dev \
        libglu1-mesa-dev && \
    python3 -m pip install --no-cache-dir -U \
        -f https://extras.wxpython.org/wxPython4/extras/linux/gtk3/debian-11 \
        wxPython && \
    python3 -m pip install --no-cache-dir -U pyinstaller python-vlc

WORKDIR /app
COPY . .
WORKDIR /app/bin
RUN python3 ./build.py -novlc && \
    mv ./install.sh ./FestEngine/ && \
    mkdir -p ./FestEngine/locale/ru/LC_MESSAGES && \
    msgfmt -o ./FestEngine/locale/ru/LC_MESSAGES/main.mo \
           ../src/locale/ru/LC_MESSAGES/main.po
RUN tar -zcvf fest_engine.tar.gz FestEngine