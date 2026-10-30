from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from .database import Base, engine, get_db
from .models import Task
from .schemas import TaskCreate, TaskUpdate, TaskOut
from .nosql import (
    write_audit, get_cached_task, set_cached_task,
    invalidate_task_cache, cache_stats, audit_collection,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="NoSQL in Practice — Task Tracker",
    description="PostgreSQL + MongoDB + Redis: учебный демонстрационный проект",
    version="1.0.0",
    lifespan=lifespan,
)

@app.get("/")
def root():
    return {
        "project": "NoSQL in Practice",
        "databases": {
            "PostgreSQL": "основные данные задач",
            "MongoDB": "документы аудита",
            "Redis": "кэш задач с TTL 60 секунд",
        },
        "docs": "/docs",
    }

@app.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(data: TaskCreate, db: Session = Depends(get_db)):
    task = Task(title=data.title, description=data.description)
    db.add(task)
    db.commit()
    db.refresh(task)
    result = TaskOut.model_validate(task)
    write_audit("task_created", task.id, result.model_dump(mode="json"))
    return result

@app.get("/tasks", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db)):
    return list(db.scalars(select(Task).order_by(Task.id.desc())).all())

@app.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    cached = get_cached_task(task_id)
    if cached:
        return {"data": cached, "source": "Redis cache"}

    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result = TaskOut.model_validate(task).model_dump(mode="json")
    set_cached_task(task_id, result)
    return {"data": result, "source": "PostgreSQL"}

@app.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, data: TaskUpdate, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)

    result = TaskOut.model_validate(task)
    invalidate_task_cache(task_id)
    write_audit("task_updated", task_id, changes)
    return result

@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    deleted_title = task.title
    db.delete(task)
    db.commit()
    invalidate_task_cache(task_id)
    write_audit("task_deleted", task_id, {"title": deleted_title})
    return None

@app.get("/audit")
def get_audit(limit: int = 50):
    """Читает последние события непосредственно из MongoDB."""
    limit = max(1, min(limit, 200))
    docs = list(audit_collection.find({}, {"_id": 0}).sort("created_at", -1).limit(limit))
    for doc in docs:
        if "created_at" in doc:
            doc["created_at"] = doc["created_at"].isoformat()
    return {"count": len(docs), "events": docs}

@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    task_count = db.scalar(select(func.count()).select_from(Task))
    return {
        "postgresql": {"tasks_total": task_count},
        "redis": cache_stats(),
        "mongodb": {"audit_events_total": audit_collection.count_documents({})},
    }
