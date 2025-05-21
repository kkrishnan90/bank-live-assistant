# Stage 1: Build the React application
FROM node:18-alpine AS builder
ARG REACT_APP_BACKEND_URL

# Set the working directory
WORKDIR /app

# Copy package.json and package-lock.json (or yarn.lock)
COPY package.json package-lock.json ./

# Install dependencies
RUN npm install

# Copy the rest of the application code
COPY . .

# Set the environment variable for the backend URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

# Build the application
RUN npm run build

# Stage 2: Serve the application using Nginx
FROM nginx:stable-alpine

# Copy the built static assets from the builder stage
COPY --from=builder /app/build /usr/share/nginx/html

# Create a script to replace environment variables in JavaScript files at runtime
RUN echo '#!/bin/sh\n\
# Replace environment variables in JavaScript files\n\
find /usr/share/nginx/html -name "*.js" -exec sed -i -e "s|BACKEND_URL_PLACEHOLDER|$BACKEND_URL|g" {} \;\n\
\n\
# Start nginx\n\
exec nginx -g "daemon off;"' > /docker-entrypoint.sh \
&& chmod +x /docker-entrypoint.sh

# Copy a custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Set the entry point to our custom script
ENTRYPOINT ["/docker-entrypoint.sh"]
