from fastapi import FastAPI
from app.routers import genomes, stats
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="NCBI Genome API", version="0.1.0")
app.include_router(genomes.router)
app.include_router(stats.router)
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

@app.get("/")
async def root():
    return {"status": "ok"}