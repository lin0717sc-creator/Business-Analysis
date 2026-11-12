import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Literal
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Market Research Workflow API")
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# --- 模型定义 ---
class ExpertPersona(BaseModel):
    matrix_layer: str
    job_title: str
    insider_intel: str
    blind_spot: str
    sourcing_channels: List[str]

class PersonaResponse(BaseModel):
    personas: List[ExpertPersona]

class InterviewQuestion(BaseModel):
    question_text: str
    applied_rule: str
    counter_tactic: str

class InterviewScript(BaseModel):
    expert_title: str
    questions: List[InterviewQuestion]

class ScriptResponse(BaseModel):
    scripts: List[InterviewScript]

class RoleplayRequest(BaseModel):
    expert_title: str
    script_context: str
    chat_history: List[Dict[str, str]]
    new_message: str

class RoleplayResponse(BaseModel):
    response_type: Literal["chat", "review"]
    content: str

# --- 路由配置 ---
@app.post("/api/v1/personas", response_model=PersonaResponse)
async def generate_personas(product_domain: str):
    system_prompt = f"""
    当前赛道：{product_domain}。输出5个一线核心角色画像。
    必须返回 JSON 格式，结构如下：
    {{"personas": [{{"matrix_layer": "...", "job_title": "...", "insider_intel": "...", "blind_spot": "...", "sourcing_channels": ["..."]}}]}}
    """
    try:
        completion = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[{"role": "system", "content": system_prompt}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scripts", response_model=ScriptResponse)
async def generate_scripts(selected_experts: List[ExpertPersona]):
    if not selected_experts:
        raise HTTPException(status_code=400, detail="不能为空")
    expert_titles = [e.job_title for e in selected_experts]
    system_prompt = f"""
    基于选定受访者：{expert_titles}。设计5-7个核心问题。
    必须返回 JSON 格式，结构如下：
    {{"scripts": [{{"expert_title": "...", "questions": [{{"question_text": "...", "applied_rule": "...", "counter_tactic": "..."}}]}}]}}
    """
    try:
        completion = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[{"role": "system", "content": system_prompt}],
            response_format={"type": "json_object"},
            temperature=0.8
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/roleplay", response_model=RoleplayResponse)
async def chat_roleplay(request: RoleplayRequest):
    if request.new_message.strip() == "【复盘】":
        messages = [{"role": "system", "content": "你是一个冷酷的调研教练，请指出访谈者漏洞。"}]
        messages.extend(request.chat_history)
        completion = client.chat.completions.create(
            model="deepseek-flash",
            messages=messages,
            temperature=0.5
        )
        return RoleplayResponse(response_type="review", content=completion.choices[0].message.content)
    
    roleplay_prompt = f"扮演：{request.expert_title}。防备心重。提纲是：{request.script_context}。仅简短回复。"
    messages = [{"role": "system", "content": roleplay_prompt}]
    messages.extend(request.chat_history)
    messages.append({"role": "user", "content": request.new_message})
    
    completion = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=messages,
        temperature=0.7
    )
    return RoleplayResponse(response_type="chat", content=completion.choices[0].message.content)