# 90-second X demo — Content Copilot

Target audience: builders on X who follow #OKXAI, agent-economy folks, content-ops
people. Post from @BrunoPessoa22 with #OKXAI.

## Cold open (0:00-0:08)

**Visual:** terminal, MCP client already open (`claude-code` or `openclaw`).
**Bruno voice-over (PT-BR):**
> "Um agente autonomo que transforma qualquer podcast em conteudo pronto pra postar.
> 8 segundos. Comeca agora."

## Cut 1 — ingest (0:08-0:20)

**Visual:** paste a YouTube URL (e.g. Karpathy interview 90-min) into the agent
prompt: `content_copilot.ingest("https://youtube.com/watch?v=…")`. Terminal
returns:
```
{"session_id":"cc_a7f2…", "duration_s":5411, "segments":812}
```

**Voice-over:**
> "Um agente chama a ASP. Ela baixa, transcreve e diariza — 90 minutos viraram
> 812 pedacos com timestamps."

## Cut 2 — mine_moments (0:20-0:40)

**Visual:** call `content_copilot.mine_moments(top_k=3)`. Response shows 3 ranked
moments with quotes + confidence scores:
```
[
 {"moment_id":"…001", "confidence":94.2, "quote":"…"},
 {"moment_id":"…027", "confidence":91.8, "quote":"…"},
 {"moment_id":"…044", "confidence":88.5, "quote":"…"}
]
```

**Voice-over:**
> "Um LLM ranqueia por novidade, tensao, aposta e quotabilidade. Os pesos foram
> treinados em 1200 rejeicoes reais do nosso fleet — nao e demo, e producao."

## Cut 3 — pack (0:40-1:05)

**Visual:** call `content_copilot.pack(target="x", voice_profile="bruno-pt-br")`.
Response returns a tweet:
```
{"kind":"single", "tweets":["…"]}
```
Show side-by-side: the tweet in Bruno's voice next to a "generic AI" version — the
difference is obvious.

**Voice-over:**
> "Escolhe o canal — X, LinkedIn, Reel, newsletter — e escolhe a voz. Sai tweet
> ja formatado, na sua voz, respeitando limite de caracteres e regras do canal."

## Cut 4 — ship (1:05-1:20)

**Visual:** call `content_copilot.ship(pack_id="…", credentials_ref="typefully-bp")`.
Response returns a Typefully share URL. Click it — the tweet is live.

**Voice-over:**
> "Publicou. Custo total: $4.50 no X Layer. Pra comparar: freelance de short-form
> custa entre $50 e $150. O agente paga pelo servico do agente — e o mercado da OKX.AI."

## Close (1:20-1:30)

**Visual:** Bruno on camera, quick shot. Overlay text: "Content Copilot on OKX.AI.
#OKXAI #OKXAIGenesisHackathon".

**Voice-over:**
> "Isso e um ASP na OKX.AI. Link no perfil. Bora construir."

## Production notes

- **Length:** ≤90s hard cap.
- **No music.** Terminal audio + voice-over only. Feels real.
- **Subtitles:** burn PT-BR + EN side-by-side, FontSize 12 Bold 0 Alignment 2 MarginV
  300 (per Bruno-voice subtitle rule).
- **First 8s** must earn the watch — cold open is the whole game.
- **Post the raw pack.json + repo link** in the reply thread as social proof.
- Include `#OKXAI` in the main post per hackathon rules.
