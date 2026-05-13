# Deploying ArogyaMitra Backend to Railway

This guide walks you through deploying your FastAPI Python backend and PostgreSQL database to Railway.

## Prerequisites
1. A GitHub account.
2. A Railway account ([railway.app](https://railway.app)).

## Step 1: Push to GitHub
1. Create a new repository on GitHub (e.g., `arogyamitra-backend`).
2. Open a terminal in the `backend/` folder of this project.
3. Run the following commands:
   ```bash
   git init
   git add .
   git commit -m "Initial backend commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/arogyamitra-backend.git
   git push -u origin main
   ```

## Step 2: Create a Railway Project
1. Log into your [Railway Dashboard](https://railway.app/dashboard).
2. Click **New Project** -> **Deploy from GitHub repo**.
3. Select the `arogyamitra-backend` repository.
4. Railway will immediately start building your project using the `railway.json` and `Procfile` we created. It will use the Python Nixpacks builder.

## Step 3: Add PostgreSQL Database
1. In your new Railway project, click **New** (or right click the canvas) -> **Database** -> **Add PostgreSQL**.
2. Railway will provision a Postgres database.
3. Once the database is ready, click on the **PostgreSQL** service in the canvas.
4. Go to the **Variables** tab of the PostgreSQL service. You will see a `DATABASE_URL` variable.

## Step 4: Configure Backend Environment Variables
1. Click on your **Web service** (the one deployed from GitHub).
2. Go to the **Variables** tab.
3. Click **New Variable** -> **Reference Variable**. Select the `DATABASE_URL` from the PostgreSQL service.
4. Add the following additional variables manually:
   - `OPENAI_API_KEY`: Your OpenAI API key (for ChatGPT).
   - `ANTHROPIC_API_KEY`: Your Anthropic API key (if using Claude).
   - `SECRET_KEY`: Generate a random string (e.g., `openssl rand -hex 32` or just type a long secure password).

## Step 5: Database Migrations
We have configured Alembic for you! Whenever your app restarts or deploys on Railway, it automatically runs:
```bash
alembic upgrade head
```
This means as soon as you add the `DATABASE_URL`, Railway will run the migration and automatically create all your tables in PostgreSQL before launching the API.

## Step 6: Connect your Flutter App
1. Go to the **Settings** tab of your Web service on Railway.
2. Click **Generate Domain**. Railway will give you a public URL (e.g., `https://arogyamitra-production.up.railway.app`).
3. In your Flutter app, go to `lib/services/api_service.dart`.
4. Update the `baseUrl` to point to your new Railway domain:
   ```dart
   final String baseUrl = 'https://arogyamitra-production.up.railway.app';
   ```
5. Rebuild your Android APK. Your mobile app is now live!
