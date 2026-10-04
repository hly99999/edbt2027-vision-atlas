"""Redesign the two vision-paper figures using an evidence-chain visual language.

The SVGs are the editable sources. The PDFs are generated with ReportLab so the
paper keeps vector artwork without requiring a system LaTeX installation.
"""
from __future__ import annotations

from pathlib import Path
import sys


ARCHITECTURE_SVG = r"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="620" viewBox="0 0 1200 620">
<defs>
  <marker id="arrow-orange" markerWidth="12" markerHeight="12" refX="9" refY="4" orient="auto"><path d="M0,0 L0,8 L10,4 z" fill="#df7438"/></marker>
  <marker id="arrow-blue" markerWidth="12" markerHeight="12" refX="9" refY="4" orient="auto"><path d="M0,0 L0,8 L10,4 z" fill="#23658e"/></marker>
  <marker id="arrow-red" markerWidth="12" markerHeight="12" refX="9" refY="4" orient="auto"><path d="M0,0 L0,8 L10,4 z" fill="#c74646"/></marker>
</defs>
<style>
  .title{font:bold 28px Arial;fill:#17324d}
  .step{font:bold 17px Arial;fill:#17324d}
  .subtitle{font:14px Arial;fill:#587080}
  .panel{fill:#ffffff;stroke:#174a6e;stroke-width:3}
  .panelHead{font:bold 17px Arial;fill:#17324d}
  .card{fill:#eef5fa;stroke:#8eabba;stroke-width:1.5}
  .cardGreen{fill:#eef8ee;stroke:#75a475;stroke-width:1.5}
  .cardWarm{fill:#fff4e8;stroke:#e0a064;stroke-width:1.5}
  .cardPurple{fill:#f3eefc;stroke:#9c82c5;stroke-width:1.5}
  .label{font:bold 14px Arial;fill:#36556b}
  .body{font:14px Arial;fill:#203642}
  .small{font:12px Arial;fill:#587080}
  .tiny{font:11px Arial;fill:#587080}
  .green{font:bold 13px Arial;fill:#4e7d45}
  .orange{font:bold 13px Arial;fill:#b75c2d}
  .red{font:bold 13px Arial;fill:#b23434}
  .purple{font:bold 13px Arial;fill:#6d469f}
  .chip{fill:#f7fafc;stroke:#a8bac5;stroke-width:1}
  .dash{fill:none;stroke:#6b9b6b;stroke-width:2.5;stroke-dasharray:7 6}
</style>
<rect width="1200" height="620" fill="#fbfcfe"/>
<text x="600" y="34" text-anchor="middle" class="title">Evidence-grounded, version-aware theorem infrastructure</text>

<circle cx="62" cy="72" r="18" fill="#17324d"/><text x="62" y="78" text-anchor="middle" fill="white" font="bold 16px Arial">1</text>
<text x="90" y="70" class="step">SOURCE + VERSION</text><text x="90" y="90" class="subtitle">identity before interpretation</text>
<circle cx="352" cy="72" r="18" fill="#5b8f5a"/><text x="352" y="78" text-anchor="middle" fill="white" font="bold 16px Arial">2</text>
<text x="380" y="70" class="step">EVIDENCE BINDING</text><text x="380" y="90" class="subtitle">field-level pointers</text>
<circle cx="642" cy="72" r="18" fill="#df7438"/><text x="642" y="78" text-anchor="middle" fill="white" font="bold 16px Arial">3</text>
<text x="670" y="70" class="step">SCOPE RECORD</text><text x="670" y="90" class="subtitle">unknowns stay explicit</text>
<circle cx="932" cy="72" r="18" fill="#7650a9"/><text x="932" y="78" text-anchor="middle" fill="white" font="bold 16px Arial">4</text>
<text x="960" y="70" class="step">QUALIFIED GRAPH</text><text x="960" y="90" class="subtitle">relations after review</text>

<rect x="25" y="108" width="260" height="340" rx="16" class="panel"/>
<text x="45" y="138" class="panelHead">PaperVersion</text>
<rect x="45" y="154" width="220" height="56" rx="10" class="card"/>
<text x="60" y="178" class="label">Paper / PDF</text><text x="60" y="197" class="small">source file + access tier</text>
<rect x="45" y="224" width="220" height="66" rx="10" class="card"/>
<text x="60" y="248" class="label">lineage</text><text x="60" y="268" class="small">preprint - conference - journal</text><text x="60" y="283" class="small">correction / retraction events</text>
<line x1="65" y1="337" x2="240" y2="337" stroke="#174a6e" stroke-width="3"/>
<circle cx="72" cy="337" r="8" fill="#17324d"/><circle cx="155" cy="337" r="8" fill="#5b8f5a"/><circle cx="238" cy="337" r="8" fill="#df7438"/>
<text x="72" y="365" text-anchor="middle" class="tiny">v1</text><text x="155" y="365" text-anchor="middle" class="tiny">v2</text><text x="238" y="365" text-anchor="middle" class="tiny">v3</text>
<text x="45" y="402" class="tiny">hash: 848f00c3...595cf</text><text x="45" y="420" class="green">identity check  ✓</text>

<rect x="315" y="108" width="260" height="340" rx="16" class="panel"/>
<text x="335" y="138" class="panelHead">EvidencePointer</text>
<rect x="335" y="154" width="220" height="164" rx="10" class="cardGreen"/>
<text x="352" y="180" class="label">exact source binding</text>
<text x="352" y="211" class="small">label   Theorem 14</text><text x="352" y="235" class="small">page    12</text><text x="352" y="259" class="small">section  5 Algorithm</text><text x="352" y="283" class="small">span    extracted text range</text><text x="352" y="307" class="small">hash    source SHA-256</text>
<rect x="335" y="336" width="220" height="78" rx="10" class="card"/>
<text x="352" y="362" class="green">grounded fields</text><text x="352" y="386" class="small">scope, bound, probability</text><text x="352" y="404" class="small">each keeps its own pointer</text>

<rect x="605" y="108" width="260" height="340" rx="16" class="panel"/>
<text x="625" y="138" class="panelHead">ScopedTheorem</text>
<rect x="625" y="154" width="220" height="188" rx="10" class="cardWarm"/>
<text x="642" y="180" class="label">formal scope contract</text>
<rect x="642" y="198" width="93" height="28" rx="12" class="chip"/><text x="688" y="217" text-anchor="middle" class="tiny">fragment</text>
<rect x="747" y="198" width="93" height="28" rx="12" class="chip"/><text x="793" y="217" text-anchor="middle" class="tiny">roles</text>
<rect x="642" y="236" width="93" height="28" rx="12" class="chip"/><text x="688" y="255" text-anchor="middle" class="tiny">regime</text>
<rect x="747" y="236" width="93" height="28" rx="12" class="chip"/><text x="793" y="255" text-anchor="middle" class="tiny">resources</text>
<rect x="642" y="274" width="93" height="28" rx="12" class="chip"/><text x="688" y="293" text-anchor="middle" class="tiny">randomness</text>
<rect x="747" y="274" width="93" height="28" rx="12" class="chip"/><text x="793" y="293" text-anchor="middle" class="tiny">result kind</text>
<text x="642" y="325" class="orange">missing axes → UNKNOWN</text>
<rect x="625" y="360" width="220" height="54" rx="10" class="card"/>
<text x="642" y="384" class="small">promotion requires source access</text><text x="642" y="402" class="small">and field-level review</text>

<rect x="895" y="108" width="280" height="340" rx="16" class="panel"/>
<text x="915" y="138" class="panelHead">TypedRelation</text>
<rect x="915" y="154" width="240" height="102" rx="10" class="cardPurple"/>
<text x="932" y="180" class="purple">qualified graph edge</text>
<text x="932" y="207" class="small">subsumes   /   conflicts with</text><text x="932" y="229" class="small">strengthens /   uses technique</text><text x="932" y="248" class="tiny">scope preconditions + evidence</text>
<rect x="915" y="274" width="240" height="92" rx="10" class="card"/>
<text x="932" y="300" class="label">Researcher query</text><text x="932" y="326" class="small">find constant-delay results</text><text x="932" y="348" class="small">under the same query scope</text>
<text x="915" y="401" class="purple">relations are inferred last</text><text x="915" y="420" class="tiny">similarity never implies proof</text>

<line x1="285" y1="278" x2="305" y2="278" stroke="#df7438" stroke-width="4" marker-end="url(#arrow-orange)"/>
<line x1="575" y1="278" x2="595" y2="278" stroke="#df7438" stroke-width="4" marker-end="url(#arrow-orange)"/>
<line x1="865" y1="278" x2="885" y2="278" stroke="#df7438" stroke-width="4" marker-end="url(#arrow-orange)"/>

<path d="M155 452 C155 476, 640 476, 640 452" class="dash"/>
<text x="398" y="470" text-anchor="middle" class="tiny">version lineage constrains which evidence can be promoted</text>
<path d="M735 452 C735 476, 1030 476, 1030 452" class="dash"/>
<text x="882" y="470" text-anchor="middle" class="tiny">scope is preserved before typed relations</text>

<rect x="25" y="500" width="1150" height="86" rx="16" fill="#eef8ee" stroke="#6c9a69" stroke-width="2"/>
<text x="45" y="528" class="panelHead">PROMOTION GATE</text>
<rect x="245" y="513" width="130" height="42" rx="12" class="cardGreen"/><text x="310" y="538" text-anchor="middle" class="small">access check</text>
<line x1="377" y1="534" x2="395" y2="534" stroke="#23658e" stroke-width="3" marker-end="url(#arrow-blue)"/>
<rect x="405" y="513" width="130" height="42" rx="12" class="cardGreen"/><text x="470" y="538" text-anchor="middle" class="small">identity check</text>
<line x1="537" y1="534" x2="555" y2="534" stroke="#23658e" stroke-width="3" marker-end="url(#arrow-blue)"/>
<rect x="565" y="513" width="130" height="42" rx="12" class="cardGreen"/><text x="630" y="538" text-anchor="middle" class="small">field review</text>
<line x1="697" y1="534" x2="715" y2="534" stroke="#23658e" stroke-width="3" marker-end="url(#arrow-blue)"/>
<rect x="725" y="513" width="130" height="42" rx="12" class="cardGreen"/><text x="790" y="538" text-anchor="middle" class="small">sign / reject</text>
<rect x="885" y="513" width="270" height="42" rx="12" fill="#fff1ed" stroke="#d06c5c" stroke-width="1.5"/><text x="1020" y="532" text-anchor="middle" class="red">unresolved values remain explicit</text><text x="1020" y="548" text-anchor="middle" class="tiny">no silent completion</text>
<text x="600" y="610" text-anchor="middle" class="subtitle">source evidence  /  scope preservation  /  version lineage  /  qualified relations</text>
</svg>"""


RUNNING_SVG = r"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="700" viewBox="0 0 1200 700">
<defs>
  <marker id="r-arrow-orange" markerWidth="12" markerHeight="12" refX="9" refY="4" orient="auto"><path d="M0,0 L0,8 L10,4 z" fill="#df7438"/></marker>
  <marker id="r-arrow-blue" markerWidth="12" markerHeight="12" refX="9" refY="4" orient="auto"><path d="M0,0 L0,8 L10,4 z" fill="#23658e"/></marker>
</defs>
<style>
  .title{font:bold 28px Arial;fill:#17324d}.head{font:bold 18px Arial;fill:#17324d}
  .panel{fill:#ffffff;stroke:#174a6e;stroke-width:2.5}.bad{fill:#fff1ed;stroke:#d06c5c;stroke-width:2}.good{fill:#eef8ee;stroke:#6c9a69;stroke-width:2}.audit{fill:#f3eefc;stroke:#9c82c5;stroke-width:2}
  .label{font:bold 14px Arial;fill:#36556b}.body{font:15px Arial;fill:#203642}.small{font:12px Arial;fill:#587080}.tiny{font:11px Arial;fill:#587080}.red{font:bold 13px Arial;fill:#b23434}.green{font:bold 13px Arial;fill:#4e7d45}.purple{font:bold 13px Arial;fill:#6d469f}.orange{font:bold 13px Arial;fill:#b75c2d}
  .line{stroke:#b8c7d1;stroke-width:1.5}.chip{fill:#fff;stroke:#d06c5c;stroke-width:1.2}.chipGood{fill:#fff;stroke:#75a475;stroke-width:1.2}
</style>
<rect width="1200" height="700" fill="#fbfcfe"/>
<text x="600" y="34" text-anchor="middle" class="title">Flat claim -&gt; scoped theorem -&gt; evidence-backed audit</text>

<rect x="25" y="62" width="320" height="205" rx="16" class="bad"/>
<text x="45" y="91" class="head">1  FLATTENED CLAIM</text>
<text x="45" y="125" class="body">"Join queries can be evaluated</text><text x="45" y="147" class="body">efficiently in parallel."</text>
<text x="45" y="178" class="small">The sentence hides the conditions</text><text x="45" y="197" class="small">that determine what is proved.</text>
<rect x="45" y="216" width="70" height="26" rx="12" class="chip"/><text x="80" y="233" text-anchor="middle" class="tiny">query?</text>
<rect x="125" y="216" width="70" height="26" rx="12" class="chip"/><text x="160" y="233" text-anchor="middle" class="tiny">model?</text>
<rect x="205" y="216" width="70" height="26" rx="12" class="chip"/><text x="240" y="233" text-anchor="middle" class="tiny">rounds?</text>
<rect x="285" y="216" width="45" height="26" rx="12" class="chip"/><text x="307" y="233" text-anchor="middle" class="tiny">?</text>

<line x1="345" y1="164" x2="376" y2="164" stroke="#df7438" stroke-width="4" marker-end="url(#r-arrow-orange)"/>
<text x="360" y="148" text-anchor="middle" class="orange">extract</text>

<rect x="385" y="62" width="430" height="205" rx="16" class="good"/>
<text x="405" y="91" class="head">2  SCOPED THEOREM RECORD</text>
<text x="405" y="116" class="green">PAC Theorem 14</text>
<rect x="405" y="133" width="185" height="34" rx="10" class="chipGood"/><text x="497" y="155" text-anchor="middle" class="tiny">full conjunctive join</text>
<rect x="600" y="133" width="185" height="34" rx="10" class="chipGood"/><text x="692" y="155" text-anchor="middle" class="tiny">MPC, 3 rounds</text>
<rect x="405" y="177" width="185" height="34" rx="10" class="chipGood"/><text x="497" y="199" text-anchor="middle" class="tiny">per-server load</text>
<rect x="600" y="177" width="185" height="34" rx="10" class="chipGood"/><text x="692" y="199" text-anchor="middle" class="tiny">high probability</text>
<text x="405" y="237" class="small">roles: q fixed | D input | p,r,S parameters</text>
<text x="405" y="254" class="small">unknown axes remain UNKNOWN until evidence is found</text>

<line x1="815" y1="164" x2="846" y2="164" stroke="#23658e" stroke-width="4" marker-end="url(#r-arrow-blue)"/>
<text x="830" y="148" text-anchor="middle" class="green">bind</text>

<rect x="855" y="62" width="320" height="205" rx="16" class="audit"/>
<text x="875" y="91" class="head">3  EVIDENCE CHECK</text>
<text x="875" y="118" class="purple">source pointer</text>
<text x="875" y="143" class="small">Theorem 14 | PDF p.12 | Section 5</text>
<text x="875" y="166" class="small">version:0f48322c4246924097bc</text>
<text x="875" y="189" class="small">SHA-256: 848f00c3...595cf</text>
<text x="875" y="221" class="green">✓ scope  ✓ bound  ✓ probability</text>
<text x="875" y="242" class="tiny">promotion is allowed only after exact review</text>

<rect x="25" y="300" width="1150" height="285" rx="16" class="panel"/>
<text x="50" y="330" class="head">4  WHAT THE FLAT SENTENCE DROPS</text>
<rect x="50" y="350" width="510" height="202" rx="12" fill="#fff7f4" stroke="#e3a196" stroke-width="1.5"/>
<text x="75" y="379" class="red">scope axes</text>
<text x="75" y="407" class="body">query fragment: Fragment(D,r,C)</text>
<text x="75" y="432" class="body">assumptions: C adheres to spectrum r</text>
<text x="75" y="457" class="body">solution: S solves q with respect to C</text>
<text x="75" y="482" class="body">resource: O~(|D|/p^(1/c(S))) per server</text>
<text x="75" y="507" class="body">semantics: three rounds, high probability</text>
<text x="75" y="532" class="body">identity: ICDT 2025 version + source hash</text>

<rect x="590" y="350" width="560" height="202" rx="12" fill="#f6fbf6" stroke="#9abe9a" stroke-width="1.5"/>
<text x="615" y="379" class="green">field-level audit and promotion</text>
<line x1="615" y1="397" x2="1125" y2="397" class="line"/>
<text x="615" y="422" class="label">extract</text><text x="715" y="422" class="small">candidate fields with uncertainty</text>
<text x="615" y="448" class="label">locate</text><text x="715" y="448" class="small">label, page, section, span, hash</text>
<text x="615" y="474" class="label">review</text><text x="715" y="474" class="small">check scope against exact source version</text>
<text x="615" y="500" class="label">promote</text><text x="715" y="500" class="small">sign record or retain explicit UNKNOWN</text>
<rect x="615" y="517" width="500" height="25" rx="10" class="chipGood"/><text x="865" y="534" text-anchor="middle" class="tiny">flat wording is a search cue, never the theorem record</text>

<path d="M185 585 C185 618, 450 618, 450 585" fill="none" stroke="#c74646" stroke-width="2.5" stroke-dasharray="7 6"/>
<text x="317" y="640" text-anchor="middle" class="red">lost conditions = unsafe generalization</text>
<path d="M760 585 C760 618, 1020 618, 1020 585" fill="none" stroke="#6c9a69" stroke-width="2.5" stroke-dasharray="7 6"/>
<text x="890" y="640" text-anchor="middle" class="green">exact evidence = bounded promotion</text>
<text x="600" y="684" text-anchor="middle" class="small">a theorem is a scoped, versioned, evidence-bound object</text>
</svg>"""


def _write_sources(fig_dir: Path) -> None:
    fig_dir.mkdir(parents=True, exist_ok=True)
    (fig_dir / "architecture.svg").write_text(ARCHITECTURE_SVG, encoding="utf-8")
    (fig_dir / "running_example.svg").write_text(RUNNING_SVG, encoding="utf-8")


def _pdf_helpers():
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen.canvas import Canvas
    return HexColor, Canvas


def _setup(c, width: float, height: float, view_w: float, view_h: float) -> None:
    c.translate(0, height)
    c.scale(width / view_w, -height / view_h)


def _rect(c, x, y, w, h, fill, stroke="#174a6e", radius=12, line=1.5):
    from reportlab.lib.colors import HexColor
    c.setFillColor(HexColor(fill))
    c.setStrokeColor(HexColor(stroke))
    c.setLineWidth(line)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=1)


def _text(c, x, y, s, size=14, color="#203642", font="Helvetica", align="left"):
    from reportlab.lib.colors import HexColor
    # The page is drawn in SVG-style top-down coordinates.  The global
    # y-axis flip keeps shapes in that coordinate system, so text needs a
    # local counter-flip to remain upright.
    c.saveState()
    c.translate(x, y)
    c.scale(1, -1)
    c.setFont(font, size)
    c.setFillColor(HexColor(color))
    if align == "center":
        c.drawCentredString(0, 0, s)
    elif align == "right":
        c.drawRightString(0, 0, s)
    else:
        c.drawString(0, 0, s)
    c.restoreState()


def _line(c, x1, y1, x2, y2, color="#b8c7d1", width=1.5, dash=None):
    from reportlab.lib.colors import HexColor
    c.setStrokeColor(HexColor(color))
    c.setLineWidth(width)
    if dash:
        c.setDash(dash)
    else:
        c.setDash()
    c.line(x1, y1, x2, y2)
    c.setDash()


def _arrow(c, x1, y1, x2, y2, color="#df7438", width=4):
    from reportlab.lib.colors import HexColor
    c.setStrokeColor(HexColor(color))
    c.setFillColor(HexColor(color))
    c.setLineWidth(width)
    c.line(x1, y1, x2 - 10, y2)
    c.line(x2 - 18, y2 - 5, x2 - 10, y2)
    c.line(x2 - 18, y2 + 5, x2 - 10, y2)


def _circle(c, x, y, r, fill):
    from reportlab.lib.colors import HexColor
    c.setFillColor(HexColor(fill))
    c.setStrokeColor(HexColor(fill))
    c.circle(x, y, r, fill=1, stroke=0)


def _draw_architecture_pdf(out: Path) -> None:
    from reportlab.lib.pagesizes import landscape, A4
    _, Canvas = _pdf_helpers()
    W, H = landscape(A4)
    c = Canvas(str(out), pagesize=(W, H))
    _setup(c, W, H, 1200, 620)
    c.setFillColorRGB(0.985, 0.99, 1)
    c.rect(0, 0, 1200, 620, fill=1, stroke=0)
    _text(c, 600, 34, "Evidence-grounded, version-aware theorem infrastructure", 28, "#17324d", "Helvetica-Bold", "center")
    steps = [(62, "#17324d", "SOURCE + VERSION", "identity before interpretation"), (352, "#5b8f5a", "EVIDENCE BINDING", "field-level pointers"), (642, "#df7438", "SCOPE RECORD", "unknowns stay explicit"), (932, "#7650a9", "QUALIFIED GRAPH", "relations after review")]
    for x, color, heading, sub in steps:
        _circle(c, x, 72, 18, color); _text(c, x, 78, str(steps.index((x, color, heading, sub)) + 1), 16, "#ffffff", "Helvetica-Bold", "center")
        _text(c, x + 28, 70, heading, 17, "#17324d", "Helvetica-Bold"); _text(c, x + 28, 90, sub, 14, "#587080")
    xs = [25, 315, 605, 895]
    heads = ["PaperVersion", "EvidencePointer", "ScopedTheorem", "TypedRelation"]
    for x, h in zip(xs, heads):
        _rect(c, x, 108, 260 if x != 895 else 280, 340, "#ffffff", "#174a6e", 16, 2.5)
        _text(c, x + 20, 138, h, 17, "#17324d", "Helvetica-Bold")
    _rect(c, 45, 154, 220, 56, "#eef5fa", "#8eabba", 10); _text(c, 60, 178, "Paper / PDF", 14, "#36556b", "Helvetica-Bold"); _text(c, 60, 197, "source file + access tier", 12, "#587080")
    _rect(c, 45, 224, 220, 66, "#eef5fa", "#8eabba", 10); _text(c, 60, 248, "lineage", 14, "#36556b", "Helvetica-Bold"); _text(c, 60, 268, "preprint - conference - journal", 12, "#587080"); _text(c, 60, 283, "correction / retraction events", 12, "#587080")
    _line(c, 65, 337, 240, 337, "#174a6e", 3); _circle(c, 72, 337, 8, "#17324d"); _circle(c, 155, 337, 8, "#5b8f5a"); _circle(c, 238, 337, 8, "#df7438")
    for x, v in [(72, "v1"), (155, "v2"), (238, "v3")]: _text(c, x, 365, v, 11, "#587080", align="center")
    _text(c, 45, 402, "hash: 848f00c3...595cf", 11, "#587080"); _text(c, 45, 420, "identity check  [OK]", 13, "#4e7d45", "Helvetica-Bold")

    _rect(c, 335, 154, 220, 164, "#eef8ee", "#75a475", 10); _text(c, 352, 180, "exact source binding", 14, "#36556b", "Helvetica-Bold")
    for yy, s in [(211, "label   Theorem 14"), (235, "page    12"), (259, "section  5 Algorithm"), (283, "span    extracted text range"), (307, "hash    source SHA-256")]: _text(c, 352, yy, s, 12, "#587080")
    _rect(c, 335, 336, 220, 78, "#eef5fa", "#8eabba", 10); _text(c, 352, 362, "grounded fields", 13, "#4e7d45", "Helvetica-Bold"); _text(c, 352, 386, "scope, bound, probability", 12, "#587080"); _text(c, 352, 404, "each keeps its own pointer", 12, "#587080")

    _rect(c, 625, 154, 220, 188, "#fff4e8", "#e0a064", 10); _text(c, 642, 180, "formal scope contract", 14, "#36556b", "Helvetica-Bold")
    chips = [(642, 198, "fragment"), (747, 198, "roles"), (642, 236, "regime"), (747, 236, "resources"), (642, 274, "randomness"), (747, 274, "result kind")]
    for xx, yy, s in chips:
        _rect(c, xx, yy, 93, 28, "#f7fafc", "#a8bac5", 12, 1); _text(c, xx + 46, yy + 19, s, 11, "#587080", align="center")
    _text(c, 642, 325, "missing axes -> UNKNOWN", 13, "#b75c2d", "Helvetica-Bold")
    _rect(c, 625, 360, 220, 54, "#eef5fa", "#8eabba", 10); _text(c, 642, 384, "promotion requires source access", 12, "#587080"); _text(c, 642, 402, "and field-level review", 12, "#587080")

    _rect(c, 915, 154, 240, 102, "#f3eefc", "#9c82c5", 10); _text(c, 932, 180, "qualified graph edge", 13, "#6d469f", "Helvetica-Bold"); _text(c, 932, 207, "subsumes / conflicts with", 12, "#587080"); _text(c, 932, 229, "strengthens / uses technique", 12, "#587080"); _text(c, 932, 248, "scope preconditions + evidence", 11, "#587080")
    _rect(c, 915, 274, 240, 92, "#eef5fa", "#8eabba", 10); _text(c, 932, 300, "Researcher query", 14, "#36556b", "Helvetica-Bold"); _text(c, 932, 326, "find constant-delay results", 12, "#587080"); _text(c, 932, 348, "under the same query scope", 12, "#587080")
    _text(c, 915, 401, "relations are inferred last", 13, "#6d469f", "Helvetica-Bold"); _text(c, 915, 420, "similarity never implies proof", 11, "#587080")
    _arrow(c, 285, 278, 305, 278); _arrow(c, 575, 278, 595, 278); _arrow(c, 865, 278, 885, 278)
    _line(c, 25, 500, 1175, 500, "#6c9a69", 1)
    _rect(c, 25, 500, 1150, 86, "#eef8ee", "#6c9a69", 16, 2); _text(c, 45, 528, "PROMOTION GATE", 17, "#17324d", "Helvetica-Bold")
    for xx, label in [(245, "access check"), (405, "identity check"), (565, "field review"), (725, "sign / reject")]:
        _rect(c, xx, 513, 130, 42, "#eef8ee", "#75a475", 12); _text(c, xx + 65, 538, label, 12, "#587080", align="center")
    _arrow(c, 377, 534, 395, 534, "#23658e", 3); _arrow(c, 537, 534, 555, 534, "#23658e", 3); _arrow(c, 697, 534, 715, 534, "#23658e", 3)
    _rect(c, 885, 513, 270, 42, "#fff1ed", "#d06c5c", 12); _text(c, 1020, 532, "unresolved values remain explicit", 12, "#b23434", "Helvetica-Bold", align="center"); _text(c, 1020, 548, "no silent completion", 11, "#587080", align="center")
    _text(c, 600, 610, "source evidence  /  scope preservation  /  version lineage  /  qualified relations", 14, "#587080", align="center")
    c.save()


def _draw_running_pdf(out: Path) -> None:
    from reportlab.lib.pagesizes import landscape, A4
    _, Canvas = _pdf_helpers()
    W, H = landscape(A4)
    c = Canvas(str(out), pagesize=(W, H))
    _setup(c, W, H, 1200, 700)
    c.setFillColorRGB(0.985, 0.99, 1); c.rect(0, 0, 1200, 700, fill=1, stroke=0)
    _text(c, 600, 34, "Flat claim -> scoped theorem -> evidence-backed audit", 28, "#17324d", "Helvetica-Bold", "center")
    _rect(c, 25, 62, 320, 205, "#fff1ed", "#d06c5c", 16, 2); _text(c, 45, 91, "1  FLATTENED CLAIM", 18, "#17324d", "Helvetica-Bold"); _text(c, 45, 125, '"Join queries can be evaluated', 15); _text(c, 45, 147, 'efficiently in parallel."', 15); _text(c, 45, 178, "The sentence hides the conditions", 12, "#587080"); _text(c, 45, 197, "that determine what is proved.", 12, "#587080")
    for xx, s, ww in [(45, "query?", 70), (125, "model?", 70), (205, "rounds?", 70), (285, "?", 45)]: _rect(c, xx, 216, ww, 26, "#ffffff", "#d06c5c", 12, 1); _text(c, xx + ww / 2, 233, s, 11, "#587080", align="center")
    _arrow(c, 345, 164, 376, 164); _text(c, 360, 148, "extract", 13, "#b75c2d", "Helvetica-Bold", align="center")

    _rect(c, 385, 62, 430, 205, "#eef8ee", "#6c9a69", 16, 2); _text(c, 405, 91, "2  SCOPED THEOREM RECORD", 18, "#17324d", "Helvetica-Bold"); _text(c, 405, 116, "PAC Theorem 14", 13, "#4e7d45", "Helvetica-Bold")
    for xx, yy, s in [(405, 133, "full conjunctive join"), (600, 133, "MPC, 3 rounds"), (405, 177, "per-server load"), (600, 177, "high probability")]: _rect(c, xx, yy, 185, 34, "#ffffff", "#75a475", 10, 1); _text(c, xx + 92, yy + 22, s, 11, "#587080", align="center")
    _text(c, 405, 237, "roles: q fixed | D input | p,r,S parameters", 12, "#587080"); _text(c, 405, 254, "unknown axes remain UNKNOWN until evidence is found", 12, "#587080")
    _arrow(c, 815, 164, 846, 164, "#23658e"); _text(c, 830, 148, "bind", 13, "#4e7d45", "Helvetica-Bold", align="center")

    _rect(c, 855, 62, 320, 205, "#f3eefc", "#9c82c5", 16, 2); _text(c, 875, 91, "3  EVIDENCE CHECK", 18, "#17324d", "Helvetica-Bold"); _text(c, 875, 118, "source pointer", 13, "#6d469f", "Helvetica-Bold"); _text(c, 875, 143, "Theorem 14 | PDF p.12 | Section 5", 12, "#587080"); _text(c, 875, 166, "version:0f48322c4246924097bc", 12, "#587080"); _text(c, 875, 189, "SHA-256: 848f00c3...595cf", 12, "#587080"); _text(c, 875, 221, "[OK] scope  [OK] bound  [OK] probability", 13, "#4e7d45", "Helvetica-Bold"); _text(c, 875, 242, "promotion is allowed only after exact review", 11, "#587080")

    _rect(c, 25, 300, 1150, 285, "#ffffff", "#174a6e", 16, 2); _text(c, 50, 330, "4  WHAT THE FLAT SENTENCE DROPS", 18, "#17324d", "Helvetica-Bold")
    _rect(c, 50, 350, 510, 202, "#fff7f4", "#e3a196", 12, 1.5); _text(c, 75, 379, "scope axes", 13, "#b23434", "Helvetica-Bold")
    for yy, s in [(407, "query fragment: Fragment(D,r,C)"), (432, "assumptions: C adheres to spectrum r"), (457, "solution: S solves q with respect to C"), (482, "resource: O~(|D|/p^(1/c(S))) per server"), (507, "semantics: three rounds, high probability"), (532, "identity: ICDT 2025 version + source hash")]: _text(c, 75, yy, s, 15, "#203642")
    _rect(c, 590, 350, 560, 202, "#f6fbf6", "#9abe9a", 12, 1.5); _text(c, 615, 379, "field-level audit and promotion", 13, "#4e7d45", "Helvetica-Bold"); _line(c, 615, 397, 1125, 397)
    for yy, k, s in [(422, "extract", "candidate fields with uncertainty"), (448, "locate", "label, page, section, span, hash"), (474, "review", "check scope against exact source version"), (500, "promote", "sign record or retain explicit UNKNOWN")]: _text(c, 615, yy, k, 14, "#36556b", "Helvetica-Bold"); _text(c, 715, yy, s, 12, "#587080")
    _rect(c, 615, 517, 500, 25, "#ffffff", "#75a475", 10, 1); _text(c, 865, 534, "flat wording is a search cue, never the theorem record", 11, "#587080", align="center")
    _line(c, 185, 585, 450, 585, "#c74646", 2, [7, 6]); _text(c, 317, 640, "lost conditions = unsafe generalization", 13, "#b23434", "Helvetica-Bold", align="center")
    _line(c, 760, 585, 1020, 585, "#6c9a69", 2, [7, 6]); _text(c, 890, 640, "exact evidence = bounded promotion", 13, "#4e7d45", "Helvetica-Bold", align="center")
    _text(c, 600, 684, "a theorem is a scoped, versioned, evidence-bound object", 12, "#587080", align="center")
    c.save()


def main(fig_dir: str | Path | None = None) -> None:
    if fig_dir is None:
        fig_dir = Path(__file__).resolve().parents[1] / "paper" / "edbt2027_vision" / "figures"
    fig_dir = Path(fig_dir)
    _write_sources(fig_dir)
    _draw_architecture_pdf(fig_dir / "architecture.pdf")
    _draw_running_pdf(fig_dir / "running_example.pdf")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
