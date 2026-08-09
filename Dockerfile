# Cloud Run runs this as a container. It builds it for you from source via
# `gcloud run deploy --source .` — you never need Docker installed locally.
FROM node:22-slim

WORKDIR /app

COPY package*.json ./
RUN npm install --omit=dev

COPY . .

# Cloud Run injects PORT at runtime and expects the container to listen on it —
# server.js already reads process.env.PORT, so no code change needed here.
ENV NODE_ENV=production
EXPOSE 8080

CMD ["node", "server.js"]
