## Базовый образ Node.js
FROM node:20.9.0-alpine

## Рабочая директория внутри контейнера
WORKDIR /app

## Отключаем телеметрию Next.js
ENV NEXT_TELEMETRY_DISABLED=1

## Системные зависимости
RUN apk add --no-cache \
    bash \
    git \
    curl \
    vim

## Устанавливаем claude-code глобально (для автоматизации)
RUN npm install -g @anthropic-ai/claude-code

## Сначала только package.json для кеша зависимостей
COPY package.json ./

## Установка зависимостей Node.js
RUN npm install

## Копируем остальной исходный код
COPY . .

## Делаем скрипт установки исполняемым
RUN chmod +x ./setup.sh

## Порт фронтенда
EXPOSE 3000

## Команда по умолчанию — запуск setup.sh
CMD ["/bin/bash", "./setup.sh"]


