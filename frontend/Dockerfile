FROM node:20-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Serve with a simple Node.js static server instead of nginx
FROM node:20-alpine

RUN npm install -g serve

COPY --from=build /app/dist /app/dist

EXPOSE 8080

CMD ["serve", "-s", "/app/dist", "-l", "8080"]
