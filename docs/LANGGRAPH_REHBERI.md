# LangChain ve LangGraph Rehberi — Bu Proje Üzerinden

Bu rehber, `incident-agent` projesindeki gerçek kodu kullanarak LangChain ve LangGraph'ın **ne olduğunu**, **neden kullanıldığını** ve **nasıl çalıştığını** anlatır. Sırayla oku. Her bölüm bir öncekinin üstüne kurulur.

---

## 0. Büyük resim: Bir "ajan" aslında nedir?

Bir LLM (büyük dil modeli) tek başına sadece şunu yapar: **metin alır, metin döndürür**. Dosya okuyamaz, veritabanına bakamaz, karar ağacı izleyemez.

Gerçek bir problemi çözmek için LLM'in etrafına bir **iş akışı** kurmak gerekir:

```
log dosyasını oku → hataları say → olay var mı? → (varsa) geçmişe bak → LLM'e sor → kaydet
```

Bu projede:

| Katman | Görevi | Kullanılan araç |
|---|---|---|
| **LLM ile konuşmak** | Mesaj formatı, model çağrısı, model değiştirme | **LangChain** (`langchain_core`, `langchain_ollama`) |
| **İş akışını yönetmek** | Adımlar, sıralama, koşullu dallanma, ortak durum | **LangGraph** |
| **Modeli çalıştırmak** | Modeli yerel GPU'da çalıştırmak | **Ollama** |
| **Hafıza (RAG)** | Benzer geçmiş olayları bulmak | **ChromaDB** |

Kısaca **LangChain "LLM ile nasıl konuşurum?"** sorusunu, **LangGraph ise "adımları hangi sırayla, hangi koşulla çalıştırırım?"** sorusunu çözer.

---

## 1. LangChain: LLM'lerle konuşmanın ortak dili

### 1.1 Problem

Her LLM sağlayıcısının (OpenAI, Anthropic, Ollama…) API'si farklıdır. Kodunu tek bir sağlayıcıya göre yazarsan modeli değiştirmek zorlaşır.

### 1.2 Çözüm: Ortak arayüz

LangChain her model için aynı arayüzü sunar. Bu projede [rca_llm.py](../src/incident_agent/nodes/rca_llm.py) dosyası şöyle kullanır:

```python
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

llm = ChatOllama(
    model="qwen3.5:9b",                  # hangi model
    base_url="http://localhost:11434",   # Ollama sunucusu
    temperature=0.2,                     # düşük = daha tutarlı, az "yaratıcı"
    format="json",                       # çıktıyı geçerli JSON'a zorla
    reasoning=False,                     # qwen3.x "düşünme" modunu kapat
)

cevap = llm.invoke([
    SystemMessage(content="Sen bir SRE uzmanısın. Sadece JSON döndür."),
    HumanMessage(content="Son 40 log satırı: ..."),
])
print(cevap.content)   # modelin ürettiği metin
```

Burada üç kavram var:

1. **Chat model (`ChatOllama`)**: Bir LLM'i temsil eden nesne. `ChatOpenAI` ya da `ChatAnthropic` ile değiştirsen kodun geri kalanı aynı kalır. Model değiştirmek bu kadar kolay olduğu için projede model adı sadece `.env` dosyasında yazılı.
2. **Mesajlar**:
   - `SystemMessage` modelin **rolünü ve kurallarını** belirler ("Sen SRE'sin, sadece JSON yaz").
   - `HumanMessage` **asıl soruyu ve veriyi** taşır (loglar, hata sayısı, servisler).
   - Model cevabı `AIMessage` olarak döner, metni `.content` içindedir.
3. **`.invoke()`**: LangChain'deki hemen her şeyin (model, zincir, graf) çalıştırma metodu. LangGraph'ta da aynı ismi göreceksin.

### 1.3 Yapılandırılmış çıktı (structured output)

LLM serbest metin üretir ama kodumuz **liste ve alan** bekler. Bu projede bu sorun üç katmanda çözülüyor:

```python
class RCAResult(BaseModel):          # 1) Pydantic ile beklenen şema
    summary: str
    root_causes: List[str]
    actions: List[str]
    questions: List[str]

llm = ChatOllama(..., format="json")  # 2) Ollama'ya "sadece JSON üret" kısıtı

data = _extract_json_object(raw)      # 3) Yine de bozuk gelirse temizle / yedek ayrıştırıcı
result = RCAResult.model_validate(data)
```

> **Önemli ders:** LLM çıktısına asla körü körüne güvenme. Doğrula (Pydantic), bozuk gelirse yedek yol izle (`_fallback_from_text`). Kritik kısımlar için de kural tabanlı korkuluk koy: `_apply_guardrails`, LLM hiç aksiyon üretemezse en sık görülen olaya göre hazır bir aksiyon listesi kullanır.

### 1.4 "Thinking" (düşünme) modelleri

`qwen3`, `qwen3.5` ve `qwen3.8` gibi modeller cevap vermeden önce uzun bir iç akıl yürütme (`<think>...</think>`) üretebilir. Bu kaliteyi artırabilir ama:
- Çok daha yavaştır (yüzlerce ekstra token üretir).
- Eski sürümlerde bu metin cevabın içine karışıp JSON ayrıştırmayı bozabiliyordu.

Projede bunu `.env` içindeki `OLLAMA_REASONING` ayarı yönetiyor:
- `false`: Düşünme kapalı, hızlı (varsayılan).
- `true`: Düşünme açık. LangChain düşünce metnini cevaptan ayrı bir alana koyar, JSON bozulmaz.

---

## 2. LangGraph: İş akışını bir graf olarak yazmak

### 2.1 Neden sadece fonksiyon çağırmıyoruz?

Şöyle de yazabilirdik:

```python
state = ingest(state)
state = detect(state)
if state["is_incident"]:
    state = rag_retrieve(state)
    state = rca(state)
    ...
```

Küçük projede bu çalışır. Ama akış büyüdükçe (döngüler, paralel adımlar, insan onayı, hata sonrası kaldığı yerden devam etme) bu `if` yığını yönetilemez hale gelir. LangGraph akışı **açık bir veri yapısı** olarak tanımlamanı sağlar. Böylece akış görselleştirilebilir, test edilebilir ve genişletilebilir olur.

### 2.2 Üç temel kavram: State, Node, Edge

```
        ┌──────────── STATE (ortak sözlük) ────────────┐
        │ log_path, recent_logs, error_count, severity,│
        │ summary, likely_root_causes, ...             │
        └──────────────────────────────────────────────┘
               ▲ okur / günceller     ▲
   NODE ──edge──▶ NODE ──edge──▶ NODE ...
```

#### State: Herkesin paylaştığı defter

[state.py](../src/incident_agent/state.py):

```python
class AgentState(TypedDict, total=False):
    log_path: str
    recent_logs: List[Dict[str, Any]]
    error_count: int
    is_incident: bool
    severity: str
    similar_past_incidents: List[Dict[str, Any]]
    summary: str
    ...
```

- `TypedDict` aslında normal bir Python sözlüğüdür, sadece hangi anahtarların olacağını belgeler.
- `total=False` bu alanların hepsinin baştan dolu olmak zorunda olmadığını söyler. Graf ilerledikçe dolarlar.
- Akış başında sadece `log_path` ve `window_lines` verilir, gerisini node'lar doldurur.

#### Node: Bir iş yapan fonksiyon

Kural basit: **state alır, (güncellenmiş) state döndürür.**

[detect.py](../src/incident_agent/nodes/detect.py):

```python
def detect_incident(state: AgentState) -> AgentState:
    logs = state.get("recent_logs", [])
    errors = [x for x in logs if x["level"] in ("ERROR", "CRITICAL")]
    state["error_count"] = len(errors)
    state["is_incident"] = state["error_count"] >= ERROR_THRESHOLD
    ...
    return state
```

Node'lar birbirini **tanımaz**. `detect` fonksiyonu kendisinden önce `ingest`'in çalıştığını bilmez, sadece state'te `recent_logs` olmasını bekler. Bu sayede her node ayrı ayrı test edilebilir.

> **Teknik not:** LangGraph, node'un döndürdüğü sözlüğü mevcut state ile **birleştirir** (her anahtar için "son yazan kazanır"). Yani sadece değişen alanları döndürmek de yeterlidir: `return {"error_count": 7}`. Projedeki `{**state, ...}` kalıbı da çalışır, sadece daha uzundur.

#### Edge: Hangi node'dan sonra hangisi gelir

[graph.py](../src/incident_agent/graph.py):

```python
g = StateGraph(AgentState)          # 1) State şemasıyla boş graf

g.add_node("ingest", ingest_file)   # 2) Node'ları isimleriyle kaydet
g.add_node("detect", detect_incident)
...

g.set_entry_point("ingest")         # 3) Başlangıç noktası
g.add_edge("ingest", "detect")      # 4) Sabit kenar: ingest → detect
```

### 2.3 Koşullu kenar (conditional edge): Grafın "if" ifadesi

LangGraph'ın asıl gücü burada:

```python
def _route(state: AgentState) -> str:
    return "rag_retrieve" if state.get("is_incident") else "notify"

g.add_conditional_edges(
    "detect",                 # bu node bittikten sonra
    _route,                   # bu fonksiyonu çalıştır,
    {"rag_retrieve": "rag_retrieve", "notify": "notify"},  # dönen değere göre buraya git
)
```

`_route` bir **yönlendirici (router)** fonksiyondur. State'e bakıp bir sonraki node'un adını döndürür. Olay yoksa LLM hiç çağrılmaz, bu da hem zaman hem GPU tasarrufu sağlar.

### 2.4 Projenin tam grafı

```
            ┌────────┐
 START ───▶ │ ingest │  log dosyasının son N satırını oku ve ayrıştır
            └───┬────┘
                ▼
            ┌────────┐
            │ detect │  ERROR/CRITICAL say, severity belirle
            └───┬────┘
       is_incident?
        ├── hayır ─────────────────────────────┐
        ▼ evet                                 │
  ┌──────────────┐                             │
  │ rag_retrieve │  ChromaDB'den benzer        │
  └──────┬───────┘  geçmiş olayları getir      │
         ▼                                     │
     ┌───────┐                                 │
     │  rca  │  LLM ile kök neden analizi      │
     └───┬───┘                                 │
         ▼                                     │
    ┌────────┐                                 │
    │ dedupe │  aynı olay az önce bildirildi mi?
    └───┬────┘                                 │
        ▼                                      ▼
    ┌────────┐ ◀───────────────────────────────┘
    │ notify │  ekrana yaz
    └───┬────┘
   is_incident?
    ├── hayır ──▶ END
    ▼ evet
 ┌───────────┐
 │ rag_store │  ChromaDB'ye + data/incidents.jsonl'e kaydet
 └─────┬─────┘
       ▼
      END
```

### 2.5 Derleme ve çalıştırma

```python
graph = g.compile()                       # grafı doğrula, çalıştırılabilir hale getir
result = graph.invoke({                   # başlangıç state'i ile çalıştır
    "log_path": "data/sample.log.jsonl",
    "window_lines": 200,
})
print(result["severity"], result["summary"])  # son state
```

`compile()` kopuk node, olmayan hedef gibi hataları baştan yakalar. `invoke()` grafı START'tan END'e kadar yürütür ve **son state'i** döndürür.

[app.py](../src/incident_agent/app.py) bunu bir döngüde yapar: log dosyası her değiştiğinde `graph.invoke(...)` çağırır ve bir önceki olayın parmak izini (`last_incident_fingerprint`) bir sonraki çalıştırmaya aktarır. Aynı olay tekrar tekrar bildirilmez.

---

## 3. RAG: Modele "hafıza" vermek

**RAG (Retrieval-Augmented Generation)**, LLM'e soru sormadan önce ilgili bilgiyi bir veritabanından bulup sorunun içine eklemektir.

Bu projede:

1. **Kaydetme** (`rag_store`): Her yeni olay bir metne dönüştürülür ("Severity: HIGH | Services: payments | Events: redis_timeout ..."). Bu metin bir **embedding modeli** (`qwen3-embedding:0.6b`) ile sayı vektörüne çevrilip ChromaDB'ye yazılır.
2. **Arama** (`rag_retrieve`): Yeni olay geldiğinde aynı şekilde vektöre çevrilir. ChromaDB **anlamca en yakın** 3 eski olayı (kosinüs benzerliği) bulur.
3. **Kullanma** (`rca`): Bulunan eski olaylar prompt'a "SIMILAR PAST INCIDENTS" başlığıyla eklenir. LLM geçmişteki çözümleri görerek daha isabetli öneri yapar.

> **Neden ayrı bir embedding modeli?** Sohbet modelleri (qwen3.5:9b) metin *üretmek* için, embedding modelleri ise metni *vektöre çevirmek* için eğitilir. Embedding modeli hem çok daha küçük ve hızlıdır hem de bu işte daha iyidir. Ayrıca her modelin vektör boyutu farklıdır. Bu yüzden projede her embedding modeli için ayrı bir ChromaDB koleksiyonu açılır (`incident_history__qwen3-embedding-0.6b`).

---

## 4. Kendin dene: Mini örnek

LLM gerektirmeyen, saniyeler içinde çalışan küçük bir graf örneği [ornek_mini_graph.py](ornek_mini_graph.py) dosyasında:

```powershell
.\.venv\Scripts\python.exe docs\ornek_mini_graph.py
```

Dosyayı aç ve değiştirmeyi dene: eşiği değiştir, yeni bir node ekle, koşulu tersine çevir.

---

## 5. Alıştırmalar (anladığını test et)

1. **Yeni node ekle:** Olay `HIGH` ise ekstra bir uyarı basan `escalate` node'u yaz ve `dedupe` ile `notify` arasına koşullu olarak ekle.
2. **Akışı optimize et:** Şu an `dedupe`, `rca`'dan **sonra** çalışıyor. Yani tekrar eden bir olay için de LLM çağrılıyor ve GPU boşa harcanıyor. `dedupe`'u `rag_retrieve`'dan önce taşı, `should_notify=False` ise doğrudan `notify`'a giden bir koşullu kenar ekle. Hangi dosyaları değiştirmen gerekti?
3. **Model karşılaştır:** `.env` içinde `OLLAMA_MODEL`'i `qwen3.5:4b`, `qwen3.5:9b` ve (VRAM'in yetiyorsa) `qwen3.8:27b` yapıp aynı log üzerinde çalıştır. Süreyi ve cevap kalitesini karşılaştır. `OLLAMA_REASONING=true` neyi değiştirdi?
4. **Grafı görselleştir:** `print(build_graph().get_graph().draw_mermaid())` çıktısını https://mermaid.live sitesine yapıştır.
5. **Akışı adım adım izle:** `graph.invoke(...)` yerine `for adim in graph.stream(state): print(adim.keys())` kullan. Her node'un sırayla nasıl çalıştığını gör.

---

## 6. Sözlük

| Terim | Anlamı |
|---|---|
| **LLM** | Büyük dil modeli. Metin alıp metin üretir (qwen3.5, llama3.1…). |
| **Ollama** | LLM'leri kendi bilgisayarında (GPU'da) çalıştıran sunucu, `localhost:11434`. |
| **LangChain** | LLM'lerle konuşmak için ortak arayüz (modeller, mesajlar, `invoke`). |
| **LangGraph** | Adımları state paylaşan bir graf olarak tanımlayıp çalıştıran kütüphane. |
| **State** | Graf boyunca taşınan ortak sözlük. |
| **Node** | State alıp state döndüren fonksiyon (bir adım). |
| **Edge** | İki node arasındaki bağlantı. **Conditional edge** state'e göre yön seçer. |
| **RAG** | Soru sormadan önce ilgili bilgiyi veritabanından bulup prompt'a eklemek. |
| **Embedding** | Metnin anlamını temsil eden sayı vektörü. |
| **Prompt** | Modele gönderilen talimat + veri. |
| **Temperature** | Rastgelelik ayarı. 0'a yakın = tutarlı, 1'e yakın = yaratıcı. |
| **Thinking / reasoning** | Modelin cevaptan önce ürettiği iç akıl yürütme. |
| **Context window (`num_ctx`)** | Modelin tek seferde "görebildiği" maksimum token sayısı. |
