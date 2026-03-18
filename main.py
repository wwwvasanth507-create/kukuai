from fastapi import FastAPI, HTTPException, Depends, status, File, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import os
import sqlite3
import re
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import sympy
from sympy import sympify, solve, limit, diff, integrate, Symbol, S
from groq import Groq

from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "nexus-default-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480 

if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY is not set in environment or .env file.")

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Math Engine
def solve_complex_math(expression: str):
    try:
        # Check if it looks like math (digits, operators, functions)
        if not re.search(r'[0-9\+\-\*\/\^\=]', expression) and not any(k in expression.lower() for k in ["sin", "cos", "tan", "log", "derivative", "integrate", "limit"]):
            return None
        
        # Simple cleanup
        clean_expr = expression.replace('^', '**').strip()
        
        # Handle equations (contains =)
        if '=' in expression:
            parts = expression.split('=')
            if len(parts) == 2:
                lhs = sympify(parts[0].replace('^', '**'))
                rhs = sympify(parts[1].replace('^', '**'))
                x = Symbol('x')
                result = solve(lhs - rhs, x)
                return f"**Equation Solved:** {expression}\n**Result:** x = {result}"
        
        # Basic expression solving
        res = sympify(clean_expr)
        if hasattr(res, 'evalf'):
            try:
                numeric = res.evalf()
                # If numeric result is different from exact result and is a number
                if numeric.is_number and str(numeric) != str(res):
                    return f"**Calculation:** {expression}\n**Exact:** {res}\n**Decimal:** {numeric}"
            except: pass
        return f"**Result:** {res}"
    except Exception:
        return None

# App Initialization
app = FastAPI()
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

SYSTEM_DB = "data/system.db"
DB_DIR = "databases"
if not os.path.exists(DB_DIR): os.makedirs(DB_DIR)

# Models
class UserCreate(BaseModel):
    username: str
    password: str
    role: str

class Token(BaseModel):
    access_token: str
    token_type: str

class ChatRequest(BaseModel):
    message: str
    mode: Optional[str] = "local" # 'local' or 'global' (admin only)

# Database/Auth Helpers
def get_db_conn():
    conn = sqlite3.connect(SYSTEM_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_user(username: str):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username: raise HTTPException(status_code=401, detail="Invalid token")
        user = get_user(username)
        if not user: raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def sync_knowledge():
    """Sync text files in DB_DIR to knowledge_index FTS5 table."""
    conn = get_db_conn()
    cursor = conn.cursor()
    
    # 1. Get currently indexed files
    cursor.execute("SELECT file_name, mtime FROM indexed_files")
    indexed = {row['file_name']: row['mtime'] for row in cursor.fetchall()}
    
    # 2. Check filesystem
    current_files = {}
    for f in os.listdir(DB_DIR):
        if f.endswith(".db"):
            fpath = os.path.join(DB_DIR, f)
            current_files[f] = os.path.getmtime(fpath)
            
    # 3. Handle deletions
    for f in list(indexed.keys()):
        if f not in current_files:
            cursor.execute("DELETE FROM knowledge_index WHERE file_name = ?", (f,))
            cursor.execute("DELETE FROM indexed_files WHERE file_name = ?", (f,))
            
    # 4. Handle additions/updates
    for f, mtime in current_files.items():
        if f not in indexed or indexed[f] < mtime:
            fpath = os.path.join(DB_DIR, f)
            try:
                # Always read as UTF-8, ignore errors
                with open(fpath, "r", encoding="utf-8", errors="ignore") as r:
                    content = r.read()
                    
                # Split content into smaller chunks for better retrieval (e.g. by Example)
                # If it's the specific Q&A format, we can split better
                chunks = []
                if "Example " in content:
                    parts = re.split(r'Example \d+\.\d+', content)
                    chunks = [p.strip() for p in parts if p.strip()]
                else:
                    # Generic chunking by paragraphs or size
                    chunks = [content[i:i+2000] for i in range(0, len(content), 1800)]
                
                # Update index
                cursor.execute("DELETE FROM knowledge_index WHERE file_name = ?", (f,))
                for chunk in chunks:
                    if len(chunk) > 10:
                        cursor.execute("INSERT INTO knowledge_index (file_name, content) VALUES (?, ?)", (f, chunk))
                
                cursor.execute("INSERT OR REPLACE INTO indexed_files (file_name, mtime) VALUES (?, ?)", (f, mtime))
            except Exception as e:
                print(f"Error indexing {f}: {e}")
                
    conn.commit()
    conn.close()

@app.on_event("startup")
async def startup_event():
    sync_knowledge()

# Endpoints
@app.post("/api/register")
async def register(user: UserCreate):
    conn = get_db_conn()
    try:
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                       (user.username, pwd_context.hash(user.password), "user"))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")
    finally: conn.close()
    return {"message": "Registered"}

@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user(form_data.username)
    if not user or not pwd_context.verify(form_data.password, user["password"]):
        raise HTTPException(status_code=400, detail="Wrong credentials")
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user["username"], "role": user["role"], "exp": expire}
    return {"access_token": jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM), "token_type": "bearer"}

@app.get("/api/me")
async def read_me(current_user=Depends(get_current_user)):
    return {"username": current_user["username"], "role": current_user["role"]}

@app.get("/api/chat/history")
async def chat_history(current_user=Depends(get_current_user)):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT message, response, mode, timestamp FROM chat_history WHERE username = ? ORDER BY timestamp ASC", (current_user["username"],))
    hist = [dict(h) for h in cursor.fetchall()]
    conn.close()
    return hist

@app.delete("/api/chat/clear")
async def clear_chat(current_user=Depends(get_current_user)):
    conn = get_db_conn()
    conn.execute("DELETE FROM chat_history WHERE username = ?", (current_user["username"],))
    conn.commit()
    conn.close()
    return {"message": "Chat history cleared"}

@app.post("/api/chat")
async def chat(request: ChatRequest, current_user=Depends(get_current_user)):
    msg = request.message.strip()
    mode = request.mode if current_user["role"] == "admin" else "local"
    
    # 1. Math
    math = solve_complex_math(msg)
    if math: response = math
    else:
        # 2. Response Logic
        if mode == "global" and current_user["role"] == "admin":
            try:
                if not groq_client: return "AI service unconfigured."
                res = groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": msg}],
                    model="llama-3.3-70b-versatile",
                )
                response = res.choices[0].message.content.strip()
            except Exception as e: 
                print(f"Global AI Error: {e}")
                response = "AI error. Try later."
        else:
            # Everyone uses Local Indexed Knowledge
            conn = get_db_conn()
            cursor = conn.cursor()
            
            # Clean msg for FTS5 (remove special characters that might break MATCH)
            clean_msg = re.sub(r'[^\w\s]', ' ', msg).strip()
            
            knowledge = []
            if clean_msg:
                # Use FTS5 search with a fallback
                try:
                    # Try phrase search first for better relevance
                    query = "SELECT content FROM knowledge_index WHERE content MATCH ? LIMIT 5"
                    cursor.execute(query, (f'"{clean_msg}"',))
                    knowledge = [row['content'] for row in cursor.fetchall()]
                    
                    # If no results, try simple keyword match
                    if not knowledge:
                        keywords = " OR ".join(clean_msg.split())
                        cursor.execute(query, (keywords,))
                        knowledge = [row['content'] for row in cursor.fetchall()]
                except:
                    # Fallback to simple LIKE if FTS5 fails for some reason
                    try:
                        cursor.execute("SELECT content FROM knowledge_index WHERE content LIKE ? LIMIT 3", (f'%{msg}%',))
                        knowledge = [row['content'] for row in cursor.fetchall()]
                    except: pass
            conn.close()

            if knowledge:
                ctx = "\n---\n".join(knowledge)
                # Keep context within reasonable limits
                if len(ctx) > 12000: ctx = ctx[:12000] + "..."
                
                try:
                    if not groq_client: return "Local AI service unconfigured."
                    res = groq_client.chat.completions.create(
                        messages=[
                            {"role": "system", "content": "You are a direct and concise assistant. Use ONLY the provided context to answer. NEVER mention 'the context', 'the database', 'provided information', source names, volumes, or Section IDs like Q1, A1, etc. Just provide the specific information requested. If the context does not contain the answer, say exactly: 'I don't know this information.'"}, 
                            {"role": "user", "content": f"Context:\n{ctx}\n\nUser Question: {msg}"}
                        ],
                        model="llama-3.1-8b-instant"
                    )
                    response = res.choices[0].message.content.strip()
                except Exception as e:
                    print(f"Local AI Error: {e}")
                    response = f"AI Error: {str(e)}"
            else:
                response = "I don't know this information."

    # 3. Save Private History
    conn = get_db_conn()
    conn.execute("INSERT INTO chat_history (username, message, response, mode) VALUES (?, ?, ?, ?)",
                 (current_user["username"], msg, response, mode))
    conn.commit()
    conn.close()
    return {"response": response}

# Admin/Trainer Endpoints
@app.post("/api/trainer/upload")
async def upload(files: List[UploadFile] = File(...), current_user=Depends(get_current_user)):
    if current_user["role"] not in ["trainer", "admin", "monitor"]: raise HTTPException(status_code=403)
    uploaded_files = []
    for file in files:
        content = await file.read()
        base_name = os.path.splitext(file.filename)[0]
        # Use more standard timestamp for sorting
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = f"{current_user['username']}_{base_name}_{ts}.db"
        fpath = os.path.join(DB_DIR, fname)
        
        counter = 1
        while os.path.exists(fpath):
            fname = f"{current_user['username']}_{base_name}_{ts}_{counter}.db"
            fpath = os.path.join(DB_DIR, fname)
            counter += 1
            
        with open(fpath, "wb") as b: b.write(content)
        uploaded_files.append(fname)
    sync_knowledge()
    return {"filenames": uploaded_files, "message": f"Uploaded {len(uploaded_files)} files"}

@app.get("/api/database/files")
async def list_files(current_user=Depends(get_current_user)):
    if current_user["role"] not in ["trainer", "monitor", "admin"]: raise HTTPException(status_code=403)
    files = []
    for f in os.listdir(DB_DIR):
        if f.endswith(".db"):
            fpath = os.path.join(DB_DIR, f)
            stat = os.stat(fpath)
            files.append({
                "name": f, 
                "size": stat.st_size,
                "mtime": stat.st_mtime
            })
    # Sort: Newest first
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files

@app.get("/api/database/content/{filename}")
async def get_content(filename: str, current_user=Depends(get_current_user)):
    if current_user["role"] not in ["monitor", "admin", "trainer"]: raise HTTPException(status_code=403)
    fpath = os.path.join(DB_DIR, os.path.basename(filename))
    if not os.path.exists(fpath): raise HTTPException(status_code=404, detail="File not found")
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f: 
            return {"content": f.read()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/database/save/{filename}")
async def save_content(filename: str, b: dict, current_user=Depends(get_current_user)):
    if current_user["role"] not in ["monitor", "admin", "trainer"]: raise HTTPException(status_code=403)
    fpath = os.path.join(DB_DIR, os.path.basename(filename))
    try:
        with open(fpath, "w", encoding="utf-8") as f: 
            f.write(b.get("content", ""))
        sync_knowledge()
        return {"message": "Saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/database/{filename}")
async def delete_db(filename: str, current_user=Depends(get_current_user)):
    if current_user["role"] not in ["admin", "trainer", "monitor"]: raise HTTPException(status_code=403)
    fpath = os.path.join(DB_DIR, os.path.basename(filename))
    if os.path.exists(fpath): os.remove(fpath)
    sync_knowledge()
    return {"message": "Deleted"}

@app.post("/api/admin/users")
async def create_user(u: UserCreate, current_user=Depends(get_current_user)):
    if current_user["role"] != "admin": raise HTTPException(status_code=403)
    conn = get_db_conn()
    conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (u.username, pwd_context.hash(u.password), u.role))
    conn.commit()
    conn.close()
    return {"message": "User created"}

@app.get("/api/admin/users")
async def all_users(current_user=Depends(get_current_user)):
    if current_user["role"] != "admin": raise HTTPException(status_code=403)
    conn = get_db_conn()
    res = [dict(u) for u in conn.execute("SELECT username, role FROM users").fetchall()]
    conn.close()
    return res

@app.delete("/api/admin/users/{username}")
async def wipe_user(username: str, current_user=Depends(get_current_user)):
    if current_user["role"] != "admin": raise HTTPException(status_code=403)
    conn = get_db_conn()
    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return {"message": "Deleted"}

@app.get("/api/admin/storage")
async def get_storage(current_user=Depends(get_current_user)):
    if current_user["role"] != "admin": raise HTTPException(status_code=403)
    t = 0
    for f in ["data", "databases", "static"]:
        if os.path.exists(f):
            for r, d, files in os.walk(f):
                for file in files: t += os.path.getsize(os.path.join(r, file))
    return {"total_storage_mb": round(t/(1024*1024), 2)}

app.mount("/static", StaticFiles(directory="static"), name="static")
@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r") as f: return f.read()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
