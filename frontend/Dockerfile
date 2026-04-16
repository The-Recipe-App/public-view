# ================================
# Stage 1 - Build frontend
# ================================
FROM node:20-alpine AS builder

ENV CI=true
WORKDIR /app

# Accept build-time variables from Railway
ARG VITE_SERVER_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_SUPABASE_REDIRECT_URI

# Make them available to Vite build
ENV VITE_SERVER_URL=$VITE_SERVER_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY
ENV VITE_SUPABASE_REDIRECT_URI=$VITE_SUPABASE_REDIRECT_URI

# Copy dependency manifests
COPY package.json package-lock.json* ./

# Install dependencies
# --legacy-peer-deps fixes npm 10 strict peer resolution failure
RUN if [ -f package-lock.json ]; then \
      npm ci --no-audit --no-fund --legacy-peer-deps; \
    else \
      npm install --no-audit --no-fund --legacy-peer-deps; \
    fi

# Copy source
COPY . .

# Build app (Vite reads env here)
RUN npm run build


# ================================
# Stage 2 - nginx production
# ================================
FROM nginx:alpine

RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html
RUN chmod -R 755 /usr/share/nginx/html

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]