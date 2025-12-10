# 🧵 Multithreaded Simulator  
A real-time **Operating System Multithreading Visualizer** built using **Flask + HTML/CSS/JS**.

---

## 🚀 How to Run the Multithreaded Simulator

### 🔧 1. Install Requirements

You need:

- Python 3.10+
- Git

Check versions:

```sh
python --version
git --version
```

---

### 📦 2. Clone the Repository

```sh
git clone https://github.com/Lovepreetsingh2006/multithreaded-simulator.git
cd multithreaded-simulator
```

---

### 🐍 3. Create & Activate Virtual Environment

#### Windows (PowerShell)

```powershell
python -m venv venv
venv\Scripts\activate
```

If you get an execution policy error:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
venv\Scripts\activate
```

#### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

---

### 📥 4. Install Dependencies

```sh
pip install -r requirements.txt
```

---

### 🚀 5. Run the Backend Server

```sh
python -m src.app
```

Expected output:

```
Running on http://127.0.0.1:5000
```

---

### 🌐 6. Open the Simulator UI

Open your browser:

👉 http://127.0.0.1:5000

---

### 🔁 7. Stop / Restart Simulator

Stop:

```sh
CTRL + C
```

Restart:

```sh
python -m src.app
```

---

## 🎉 You're All Set!

The simulator is fully interactive with:

- Thread creation  
- Scheduling algorithms (RR, FCFS, Priority)  
- Semaphores  
- Monitors  
- Real-time CPU core updates  

