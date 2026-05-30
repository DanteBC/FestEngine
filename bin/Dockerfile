FROM ubuntu:22.04

# Устанавливаем системные зависимости
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y \
        gettext \
        vlc \
        libjpeg-dev \
        zlib1g-dev \
        libgtk-3-dev \
        pkg-config \
        build-essential \
        python3 \
        python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Обновляем pip и устанавливаем колеса
RUN python3 -m pip install -U pip setuptools wheel && \
    python3 -m pip install -U typing-extensions six

# Устанавливаем wxPython из официальных сборок для Ubuntu 22.04
RUN python3 -m pip install -U \
    --no-cache-dir \
    -f https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-22.04 \
    wxPython

# Устанавливаем остальные Python зависимости
RUN python3 -m pip install -U pyinstaller python-vlc

WORKDIR /app
COPY . .
WORKDIR /app/bin

# Сборка проекта (флаг -novlc уже указан)
RUN python3 ./build.py -novlc && \
    mv ./install.sh ./FestEngine/ && \
    mkdir -p ./FestEngine/locale/ru/LC_MESSAGES && \
    msgfmt -o ./FestEngine/locale/ru/LC_MESSAGES/main.mo \
           ../src/locale/ru/LC_MESSAGES/main.po

# Упаковка результата
RUN tar -zcvf fest_engine.tar.gz FestEngine