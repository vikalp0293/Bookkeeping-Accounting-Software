# --- Stage 1: Build the Static Files ---
FROM node:18-alpine AS builder
 
WORKDIR /app
 
# Copy package files first to leverage Docker cache
COPY package.json package-lock.json ./
 
# Install dependencies cleanly (using the lockfile)
RUN npm install
 
# Copy the rest of the source code
COPY . .
 
# Pass the API URL environment variable during the build
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
 
# Build the app (creates the /app/dist folder)
RUN npm run build
 
# --- Stage 2: Serve with Nginx ---
FROM nginx:alpine
 
# Remove default Nginx config
RUN rm /etc/nginx/conf.d/default.conf
 
# Copy our custom config
COPY nginx.conf /etc/nginx/conf.d/default.conf
 
# Copy only the compiled assets from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html
 
# Expose port 80
EXPOSE 80
 
# Start Nginx
CMD ["nginx", "-g", "daemon off;"]