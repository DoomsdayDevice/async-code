// Конфигурация фронтенда: базовый URL API
// Использует переменную окружения NEXT_PUBLIC_API_BASE, либо умные значения по умолчанию

export const API_BASE: string = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api";
