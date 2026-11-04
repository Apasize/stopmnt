FROM python:3.11-alpine

# Dépendances système
RUN apk add --no-cache \
    gcc musl-dev libffi-dev openssl-dev \
    curl

# Créer un utilisateur non-root pour faire tourner l'app
# Par défaut Docker tourne en root — risque de sécurité
# Si quelqu'un exploite une faille dans l'app, il est limité à cet utilisateur
RUN addgroup -S stopmnt && adduser -S stopmnt -G stopmnt

WORKDIR /app

# Installer les dépendances en tant que root (nécessaire)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY . .

# Donner les droits à l'utilisateur stopmnt
RUN chown -R stopmnt:stopmnt /app

# Basculer sur l'utilisateur non-root
USER stopmnt

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
