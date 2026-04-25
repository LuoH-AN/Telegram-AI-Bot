"""LaTeX symbol maps for Unicode conversion."""

LATEX_SYMBOLS = {
    r"\times": "×", r"\div": "÷", r"\pm": "±", r"\mp": "∓", r"\cdot": "·", r"\ast": "∗", r"\star": "⋆", r"\circ": "∘",
    r"\ldots": "…", r"\dots": "…", r"\cdots": "⋯", r"\vdots": "⋮",
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\neq": "≠", r"\ne": "≠", r"\approx": "≈", r"\equiv": "≡",
    r"\sim": "∼", r"\propto": "∝", r"\ll": "≪", r"\gg": "≫",
    r"\to": "→", r"\rightarrow": "→", r"\leftarrow": "←", r"\Rightarrow": "⇒", r"\Leftarrow": "⇐",
    r"\leftrightarrow": "↔", r"\Leftrightarrow": "⇔", r"\mapsto": "↦", r"\uparrow": "↑", r"\downarrow": "↓",
    r"\sum": "∑", r"\prod": "∏", r"\int": "∫", r"\iint": "∬", r"\iiint": "∭", r"\oint": "∮",
    r"\in": "∈", r"\notin": "∉", r"\subset": "⊂", r"\supset": "⊃", r"\subseteq": "⊆", r"\supseteq": "⊇",
    r"\cup": "∪", r"\cap": "∩", r"\emptyset": "∅", r"\varnothing": "∅", r"\forall": "∀", r"\exists": "∃", r"\nexists": "∄",
    r"\neg": "¬", r"\land": "∧", r"\lor": "∨", r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇",
    r"\angle": "∠", r"\triangle": "△", r"\perp": "⊥", r"\parallel": "∥", r"\degree": "°", r"\prime": "′",
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\epsilon": "ε", r"\varepsilon": "ε", r"\zeta": "ζ",
    r"\eta": "η", r"\theta": "θ", r"\vartheta": "ϑ", r"\iota": "ι", r"\kappa": "κ", r"\lambda": "λ", r"\mu": "μ",
    r"\nu": "ν", r"\xi": "ξ", r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ", r"\upsilon": "υ",
    r"\phi": "φ", r"\varphi": "φ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ", r"\Xi": "Ξ", r"\Pi": "Π", r"\Sigma": "Σ",
    r"\Upsilon": "Υ", r"\Phi": "Φ", r"\Psi": "Ψ", r"\Omega": "Ω",
}

SUPERSCRIPT_MAP = str.maketrans("0123456789+-=()niax", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᵃˣ")
SUBSCRIPT_MAP = str.maketrans("0123456789+-=()aeiourx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑᵢₒᵤᵣₓ")
