"""Category definitions shared by every semantic interpreter.

Jev receives them as typed questions; the structured LLM receives the same text as its
instructions. One source keeps the conditions comparable: they differ in the model,
never in what each label means.
"""

QUESTIONS = {
    "intent": {
        "type": "choice",
        "instructions": (
            "Classifique a ÚLTIMA mensagem do usuário (campo user_message) em relação ao "
            "estado da conversa. pending_question é a pergunta do usuário que aguarda a "
            "informação pedida em assistant_request; se for null, não há pedido pendente."
        ),
        "criteria": {
            "clarification": (
                "Há pedido pendente e a mensagem o responde informando o nível acadêmico "
                "(graduação, pós-graduação ou ambos), sem fazer outra pergunta. Pode trazer "
                "detalhes como curso, período ou um pedido de desculpas."
            ),
            "level_declaration": (
                "A mensagem apenas informa o nível acadêmico do próprio usuário, sem fazer "
                "pergunta, e não responde a um pedido pendente."
            ),
            "new_question": (
                "A mensagem faz uma pergunta ou pedido novo e não responde ao pedido "
                "pendente com um nível acadêmico."
            ),
            "mixed": (
                "A mensagem contém duas intenções: informa o nível (ou cancela/responde o "
                "pedido pendente) E também faz uma pergunta nova."
            ),
            "uncertain": "Não é possível decidir com segurança entre as opções anteriores.",
        },
    },
    "declared_level": {
        "type": "choice",
        "instructions": "Qual nível acadêmico a mensagem do usuário informa?",
        "criteria": {
            "undergraduate": "Graduação (bacharelado, licenciatura, graduando).",
            "postgraduate": "Pós-graduação (mestrado, doutorado, especialização, stricto ou lato sensu).",
            "both": "Graduação e pós-graduação ao mesmo tempo, por exemplo para comparar.",
            "none": "A mensagem não informa nenhum nível acadêmico.",
        },
    },
    "level_evidence": {
        "type": "choice",
        "instructions": "Como o nível aparece na mensagem do usuário?",
        "criteria": {
            "explicit": "O nível é dito com todas as letras (ex.: 'sou do mestrado', 'graduação').",
            "indirect": "O nível só se deduz de outros dados (ex.: 'estou no 5º período').",
            "hedged": "O usuário demonstra dúvida sobre o próprio nível (ex.: 'acho que é pós').",
            "none": "Nenhum nível é mencionado.",
        },
    },
    "level_subject": {
        "type": "choice",
        "instructions": "A quem se refere o nível mencionado na mensagem do usuário?",
        "criteria": {
            "self": "Ao próprio usuário (ex.: 'sou aluna do mestrado').",
            "third_party": "A outra pessoa (amigo, irmão, orientando, alunos de uma monitoria).",
            "generic": "A um nível em geral, como tema da pergunta ou resposta ao pedido.",
            "unknown": "Nenhum nível é mencionado ou não é possível saber.",
        },
    },
    "references_pending": {
        "type": "noul",
        "instructions": "A mensagem responde ao pedido pendente do assistente (assistant_request)?",
        "criteria": {
            "true": "Responde ao pedido pendente.",
            "false": "Não responde ou não há pedido.",
        },
    },
    "has_new_question": {
        "type": "noul",
        "instructions": "A mensagem contém uma pergunta ou pedido novo de informação?",
        "criteria": {"true": "Contém pergunta ou pedido novo.", "false": "Não contém."},
    },
    "cancels_pending": {
        "type": "noul",
        "instructions": "O usuário desiste da pergunta pendente ou muda explicitamente de assunto?",
        "criteria": {"true": "Desiste ou muda de assunto.", "false": "Não."},
    },
}
