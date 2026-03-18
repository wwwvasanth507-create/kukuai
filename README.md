# Nexus AI Management System - Startup Guide

To run the application from your terminal, follow these steps:

## 1. Project Setup
Ensure you are in the project directory:
```bash
cd /home/vasanth/Desktop/KUKU
```

## 2. Initialize Database (First Time Only)
Run the initialization script to create the system database and the default admin account:
```bash
./venv/bin/python3 init_db.py
```

## 3. Run the Application
Start the FastAPI server using the virtual environment:
```bash
./venv/bin/python3 main.py
```

## 4. Access the System
Once the server starts, open your browser and navigate to:
**`http://localhost:8000`**

### Default Credentials
- **Username**: `admin`
- **Password**: `admin`

---

## 🛠 Features Refresher
- **AI Chat**: Engage with an ultra-scientific solver and Groq-powered logical assistant.
- **Admin Panel**: Manage users, monitor storage, and distill master intelligence.
- **Trainer Tools**: Upload raw text files to be automatically converted to structured databases via AI.
- **Global Knowledge**: Import "Google-scale" information on any topic directly into your project.
