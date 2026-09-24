"""Maquette SEO annotée de https://elmut.fr/produits-chien.

Rend la page réelle avec Playwright, retire le JavaScript et les traceurs,
applique les recommandations de la page Notion « Nourriture fraîche chien »
(partie Structure de l'article) et pose les encadrés verts.

Usage : .venv/bin/python scripts/build.py   (depuis ~/Documents/CODE/seo-tools pour le venv)
"""
import asyncio
import copy
import re
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "scripts" / "cache"
FONTS = ROOT / "assets" / "fonts"
SOURCE_URL = "https://elmut.fr/produits-chien"
ORIGIN = "https://elmut.fr"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"

# Polices libres (OFL) hébergées par elmut.fr : copiées en local.
OFL_FAMILIES = {"Geist", "Geist Mono", "Chango", "Inter"}
# Polices commerciales (PP Pangaia, Maison Neue) : remplacées par des équivalents Google Fonts.
SUBSTITUTES = {
    "Pangaia": "Playfair+Display:ital,wght@0,400;0,500;1,500",
    "MaisonNeue": "Archivo:wght@400;700",
}


# ---------------------------------------------------------------- rendu
async def render() -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900}, locale="fr-FR")
        await page.goto(SOURCE_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        for _ in range(20):
            await page.mouse.wheel(0, 700)
            await page.wait_for_timeout(150)
        await page.wait_for_timeout(1500)
        html = await page.content()
        await browser.close()
    (CACHE / "rendered.html").write_text(html, encoding="utf-8")
    return html


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


# ---------------------------------------------------------------- CSS et polices
def localize_css(css: str) -> str:
    """Polices OFL en local, polices commerciales neutralisées, autres URLs en absolu."""
    FONTS.mkdir(parents=True, exist_ok=True)

    def face(m):
        block = m.group(0)
        family = re.search(r"font-family:([^;]+);", block).group(1).strip().strip('"')
        if any(k in family for k in SUBSTITUTES):
            return ""  # redéfinie plus bas avec une police libre
        if family in OFL_FAMILIES:
            def dl(u):
                path = u.group(1)
                name = path.split("/")[-1].split("?")[0]
                target = FONTS / name
                if not target.exists():
                    target.write_bytes(fetch(ORIGIN + path))
                return f"url(assets/fonts/{name})"
            return re.sub(r"url\((/_next/static/media/[^)]+)\)", dl, block)
        return block

    css = re.sub(r"@font-face\{[^}]*\}", face, css)
    css = re.sub(r"url\((/[^)]+)\)", lambda m: f"url({ORIGIN}{m.group(1)})", css)
    return css


def substitute_faces() -> str:
    """@font-face qui réutilisent les noms de famille d'origine avec des fichiers libres."""
    faces = []
    specs = [
        ("Pangaia", "Playfair+Display:wght@500", "normal", "500"),
        ("Pangaia", "Playfair+Display:ital,wght@1,500", "italic", "500"),
        ("Pangaia", "Playfair+Display:wght@400", "normal", "200"),
        ("MaisonNeueExtendedBook", "Archivo:wght@400", "normal", "400"),
        ("MaisonNeueExtendedBold", "Archivo:wght@700", "normal", "700"),
    ]
    for family, query, style, weight in specs:
        css = fetch(f"https://fonts.googleapis.com/css2?family={query}&display=swap").decode()
        # dernier bloc = sous-ensemble latin
        src = re.findall(r"src: url\((https://[^)]+\.woff2)\)", css)[-1]
        name = f"{family}-{style}-{weight}.woff2"
        target = FONTS / name
        if not target.exists():
            target.write_bytes(fetch(src))
        faces.append(
            f'@font-face{{font-family:"{family}";font-style:{style};font-weight:{weight};'
            f"font-display:swap;src:url(assets/fonts/{name}) format(\"woff2\")}}"
        )
    return "\n".join(faces)


# ---------------------------------------------------------------- helpers DOM
def reco(soup, num, title, body, items=None):
    box = soup.new_tag("aside", attrs={"class": "reco", "data-reco": str(num)})
    head = soup.new_tag("p", attrs={"class": "reco-head"})
    badge = soup.new_tag("span", attrs={"class": "reco-num"})
    badge.string = str(num)
    head.append(badge)
    head.append(NavigableString(title))
    box.append(head)
    for para in body if isinstance(body, list) else [body]:
        p = soup.new_tag("p")
        p.append(BeautifulSoup(para, "html.parser"))
        box.append(p)
    if items:
        ul = soup.new_tag("ul")
        for it in items:
            li = soup.new_tag("li")
            li.append(BeautifulSoup(it, "html.parser"))
            ul.append(li)
        box.append(ul)
    return box


def find_h(soup, name, pattern):
    for h in soup.find_all(name):
        if re.search(pattern, h.get_text(" ", strip=True)) and h.get("aria-hidden") != "true":
            return h
    raise LookupError(pattern)


def set_text(tag, text):
    tag.clear()
    tag.append(NavigableString(text))


def mark_new(tag):
    tag["class"] = (tag.get("class") or []) + ["reco-new"]
    return tag


# ---------------------------------------------------------------- transformation
def build(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # 1. nettoyage : scripts, traceurs, bannière cookies, iframes
    for sel in ["script", "noscript", "iframe", "next-route-announcer", "link[rel=preload]",
                "link[rel=modulepreload]", "link[rel=canonical]", "link[rel=alternate]",
                "meta[property^='og:']", "meta[name^='twitter:']", "#axeptio_overlay", "section.Toastify"]:
        for t in soup.select(sel):
            t.decompose()
    styles = soup.find_all("style")
    main_css = max(styles, key=lambda s: len(s.text))
    for st in styles:
        if st is not main_css and ("toastify" in st.text or "Axeptio" in st.text):
            st.decompose()
    main_css.string = localize_css(main_css.text)

    head = soup.head
    for m in head.find_all("meta", attrs={"name": ["robots", "description"]}):
        m.decompose()
    head.append(soup.new_tag("meta", attrs={"name": "robots", "content": "noindex, nofollow, noarchive"}))
    head.title.string = "Maquette SEO /produits-chien | Elmut x datashake"
    faces = soup.new_tag("style")
    faces.string = substitute_faces()
    head.append(faces)
    head.append(soup.new_tag("link", attrs={"rel": "stylesheet", "href": "assets/maquette.css"}))

    # 2. liens et médias en absolu vers elmut.fr
    for t in soup.find_all(href=True):
        if t.name == "a" and t["href"].startswith("/"):
            t["href"] = ORIGIN + t["href"]
    for t in soup.find_all(src=True):
        if t["src"].startswith("/"):
            t["src"] = ORIGIN + t["src"]
    for t in soup.find_all(srcset=True):
        t["srcset"] = re.sub(r"(^|,\s*)(/)", lambda m: m.group(1) + ORIGIN + "/", t["srcset"])
    for t in soup.find_all(style=True):
        t["style"] = re.sub(r"url\((['\"]?)(/)", lambda m: f"url({m.group(1)}{ORIGIN}/", t["style"])

    n = 0

    # 3. Hero : nouveau H1, H1 actuel passé en H2
    old_h1 = soup.find("h1")
    new_h1 = soup.new_tag("h1", attrs={"class": "reco-new maquette-h1"})
    new_h1.string = "Nourriture fraîche pour chien : nos repas frais cuisinés en France"
    old_h1.insert_before(new_h1)
    old_h1.name = "h2"
    n += 1
    old_h1.parent.append(reco(
        soup, n, "Nouveau H1",
        "Ajouter un H1 au-dessus du titre actuel : <strong>« Nourriture fraîche pour chien : nos repas frais "
        "cuisinés en France »</strong>. Le H1 actuel « Remplissez son cœur, on se charge de sa gamelle » "
        "passe en H2 juste en dessous, sans changer son style.",
    ))

    # 4. Au menu : H2 optimisé, texte d'introduction, alt
    # Le H2 visible est animé et doublé d'un clone sr-only : les deux sont conservés, seul le texte change.
    menu_h2 = "Au menu : qualité, gourmandise et fraîcheur"
    h_menu = soup.find("h2", attrs={"data-has-accessible-clone": "true"})
    clone = h_menu.find_previous_sibling("h2", class_="sr-only")
    if clone:
        set_text(clone, menu_h2)
    h_menu["aria-label"] = menu_h2
    set_text(h_menu, menu_h2)
    mark_new(h_menu)
    intro = soup.new_tag("p", attrs={"class": "reco-new maquette-intro"})
    intro.string = (
        "Au quotidien, nos repas frais pour chien couvrent tous ses besoins : cinq recettes complètes et "
        "équilibrées, cuisinées en douceur à 90 °C avec des ingrédients propres à la consommation humaine. "
        "Pour le plaisir et la récompense, nos p'tites saucisses au canard complètent sa gamelle."
    )
    h_menu.insert_after(intro)
    menu_list = intro.find_next_sibling("ul")
    n += 1
    box_h2 = reco(
        soup, n, "H2 optimisé et texte d'introduction",
        ["H2 : « Au menu » devient <strong>« Au menu : qualité, gourmandise et fraîcheur »</strong>.",
         "Proposition de texte d'introduction ajoutée sous le titre (contour pointillé)."],
    )
    n += 1
    alt_map = {
        "Nos repas frais": "Boudins de repas frais pour chien Elmut",
        "Nos friandises": "Sachet de p'tites saucisses au canard, friandises pour chien Elmut",
    }
    box_alt = reco(
        soup, n, "Optimiser les alt des images",
        "Les deux visuels portent le titre de leur carte en alt. Proposition :",
        [f"« {a} » → « {b} »" for a, b in alt_map.items()],
    )
    menu_list.insert_after(box_h2)
    box_h2.insert_after(box_alt)
    for img in soup.find_all("img", alt=True):
        if img["alt"] in alt_map:
            img["alt"] = alt_map[img["alt"]]

    # 5. Nos repas frais : H2 renommé, alt des recettes
    h_repas = find_h(soup, "h2", r"^Nos repas frais$")
    set_text(h_repas, "Nos recettes de repas frais pour chien")
    mark_new(h_repas)
    recipes = {
        "Recette Poulet": "Repas frais pour chien au poulet",
        "Recette Boeuf": "Repas frais pour chien au bœuf",
        "Recette Dinde": "Repas frais pour chien à la dinde",
        "Recette Porc": "Repas frais pour chien au porc",
        "Recette Poisson": "Repas frais pour chien au saumon et au colin",
    }
    n += 1
    box = reco(
        soup, n, "H2 renommé et alt des recettes",
        ["H2 : « Nos repas frais » devient <strong>« Nos recettes de repas frais pour chien »</strong>.",
         "Optimiser les alt des images : les photos portent aujourd'hui le seul nom de la recette."],
        [f"« {a} » → « {b} »" for a, b in recipes.items()],
    )
    tagline = h_repas.find_next_sibling()
    (tagline or h_repas).insert_after(box)
    for img in soup.find_all("img", alt=True):
        if img["alt"] in recipes:
            img["alt"] = recipes[img["alt"]]

    # 6. Transition : titre conservé, alt uniquement
    h_trans = find_h(soup, "h2", r"^Passer")
    trans_alt = {
        "Transition 25%": "Gamelle de transition : 25 % de repas frais Elmut, 75 % d'ancienne alimentation",
        "Transition 50%": "Gamelle de transition : 50 % de repas frais Elmut, 50 % d'ancienne alimentation",
        "Transition 75%": "Gamelle de transition : 75 % de repas frais Elmut, 25 % d'ancienne alimentation",
        "Transition 100%": "Gamelle 100 % repas frais Elmut",
        "Plate image": "Gamelle pour chien vide",
        "Plate with food image": "Gamelle de repas frais pour chien Elmut",
    }
    n += 1
    box = reco(
        soup, n, "Optimiser les alt des images",
        "Les visuels de la transition portent des alt génériques. Proposition :",
        [f"« {a} » → « {b} »" for a, b in trans_alt.items()],
    )
    (h_trans.find_next_sibling() or h_trans).insert_after(box)
    for img in soup.find_all("img", alt=True):
        if img["alt"] in trans_alt:
            img["alt"] = trans_alt[img["alt"]]

    # 7. Nos friandises : H2 unique, proposition de contenu
    h_fri = find_h(soup, "h2", r"^Nos friandises")
    set_text(h_fri, "Nos friandises pour chien")
    mark_new(h_fri)
    fri_p = soup.find(string=re.compile("À ajouter juste avant")).find_parent("p")
    fri_p.clear()
    fri_p.append(NavigableString(
        "Pour le plaisir et la récompense, nos p'tites saucisses au canard complètent ses repas frais. "
        "Elles contiennent 70 % de canard et des ingrédients propres à la consommation humaine, séchés à "
        "basse température pour garder un goût légèrement fumé et une texture qui fait travailler la mâche. "
        "Chaque saucisse apporte 35 kcal : les friandises ne doivent pas dépasser 10 % de sa ration "
        "quotidienne. Ajoutez-les juste avant de valider votre box, si votre chien est sage, bien entendu."
    ))
    mark_new(fri_p)
    fri_p["class"] = [c for c in fri_p["class"] if not c.startswith("max-w")] + ["maquette-fri"]
    n += 1
    fri_p.insert_after(reco(
        soup, n, "H2 optimisé et contenu",
        ["H2 : « Nos friandises » devient <strong>« Nos friandises pour chien »</strong>.",
         "Proposition de contenu à la place de l'accroche actuelle (contour pointillé), à partir de la fiche "
         "des p'tites saucisses : 70 % de canard, séchage à basse température, 35 kcal par saucisse."],
    ))

    # 8. FAQ : H2 renommé, questions en H3, 4 questions ajoutées
    h_faq = find_h(soup, "h2", r"questions")
    set_text(h_faq, "Questions fréquentes sur notre nourriture fraîche")
    mark_new(h_faq)
    details = soup.find_all("details")
    for d in details:
        q = d.summary.find("p")
        q.name = "h3"
    n += 1
    h_faq.insert_after(reco(
        soup, n, "Questions de la FAQ en H3",
        ["Passer les questions de la FAQ en H3 : elles sont aujourd'hui dans des balises p à l'intérieur "
         "des summary.",
         "H2 : « Les questions fraîches » devient <strong>« Questions fréquentes sur notre nourriture "
         "fraîche »</strong>."],
    ))
    new_qa = [
        ("Quelle quantité de nourriture fraîche donner à mon chien par jour ?",
         "La bonne quantité dépend de son poids, de son âge, de sa stérilisation et de son niveau d'activité. "
         "C'est pourquoi chaque plan Elmut est calculé à partir du questionnaire : vous recevez des portions "
         "déjà adaptées à votre chien, sans rien avoir à peser."),
        ("La nourriture fraîche convient-elle aux chiots ?",
         "Oui, dès 4 mois. Nos recettes respectent les recommandations de la FEDIAF pour les chiots de 4 mois "
         "et plus, comme pour les chiens adultes et seniors de toutes races."),
        ("Mon chien est en surpoids, puis-je lui donner des repas frais ?",
         "Oui. Les réponses au questionnaire permettent d'ajuster les quantités à son poids et à son objectif."),
        ("Combien de temps se conservent les repas frais pour chien ?",
         "Au réfrigérateur, jusqu'à la date indiquée sur l'étiquette, puis 5 jours après ouverture du boudin. "
         "Au congélateur, jusqu'à six mois."),
    ]
    last = details[-1]
    n += 1
    box_faq = reco(
        soup, n, "Questions à ajouter à la FAQ existante (et au balisage FAQPage)",
        "Quatre questions tirées des « Autres questions posées » de Google et des faits publiés sur elmut.fr. "
        "Elles sont ouvertes ci-dessous pour la relecture.",
    )
    last.insert_after(box_faq)
    anchor = box_faq
    for q, a in new_qa:
        clone = copy.copy(last)
        clone.summary.find("h3").string = q
        answer = clone.find_all("p")[-1]
        answer.string = a
        clone["open"] = ""
        clone["data-open"] = "true"
        mark_new(clone)
        anchor.insert_after(clone)
        anchor = clone

    # 9. Contenu de bas de page, après la FAQ
    faq_section = h_faq.find_parent("section")
    bottom = BeautifulSoup(BOTTOM_HTML, "html.parser").section
    faq_section.insert_after(bottom)
    n += 1
    bottom.find("div", class_="maquette-container").insert(0, reco(
        soup, n, "Contenu de bas de page (à placer après la FAQ, avant le footer)",
        "Environ 650 mots, centrés sur la requête « nourriture fraîche chien » et ses variantes "
        "(repas frais pour chien, alimentation fraîche pour chien). Liens internes vers les 5 recettes, "
        "la page Le frais et le tunnel d'essai.",
    ))

    # 10. Bandeau et légende en haut de page
    body = soup.body
    banner = BeautifulSoup(BANNER_HTML.replace("{N}", str(n)), "html.parser")
    body.insert(0, banner)
    body.append(BeautifulSoup(TOGGLE_JS, "html.parser"))
    return str(soup)


BANNER_HTML = """
<div class="maquette-banner">
  <div class="maquette-banner-inner">
    <p class="maquette-kicker">Maquette SEO · proposition datashake · septembre 2026</p>
    <p class="maquette-title">elmut.fr/produits-chien · requête cible « nourriture fraîche chien »</p>
    <p class="maquette-legend">
      <span class="legend-box"></span> {N} recommandations en encadré vert
      <span class="legend-new"></span> contenu modifié ou ajouté en pointillés verts
    </p>
    <button type="button" class="maquette-toggle" aria-pressed="false">Masquer les recommandations</button>
  </div>
</div>
"""

TOGGLE_JS = """
<script>
document.querySelector('.maquette-toggle').addEventListener('click', function () {
  var hidden = document.body.classList.toggle('recos-hidden');
  this.textContent = hidden ? 'Afficher les recommandations' : 'Masquer les recommandations';
  this.setAttribute('aria-pressed', hidden);
});
</script>
"""

BOTTOM_HTML = """
<section class="maquette-bottom reco-new-section">
 <div class="maquette-container">
  <h2>La nourriture fraîche pour chien, cuisinée comme pour vous</h2>
  <p>Chez Elmut, la nourriture fraîche pour chien part d'un principe simple : mettre dans sa gamelle ce que vous
  pourriez mettre dans votre assiette. Tous nos ingrédients sont propres à la consommation humaine : du
  <a href="https://elmut.fr/produits-chien/frais/poulet">vrai poulet</a>, du
  <a href="https://elmut.fr/produits-chien/frais/boeuf">bœuf</a>, de la
  <a href="https://elmut.fr/produits-chien/frais/dinde">dinde</a>, du
  <a href="https://elmut.fr/produits-chien/frais/porc">porc</a>, du
  <a href="https://elmut.fr/produits-chien/frais/poisson">saumon et du colin</a>, accompagnés de légumes comme
  la courgette et la carotte. Nos repas frais pour chien sont cuisinés dans notre atelier en Poitou-Charentes,
  puis livrés directement chez vous.</p>
  <p>Nos recettes sont formulées avec des experts en nutrition canine, dans le respect des recommandations de la
  FEDIAF, la Fédération européenne de l'industrie des aliments pour animaux familiers. Chaque repas est un aliment
  complet et équilibré, complété par notre mélange maison de vitamines et de minéraux, pour couvrir les besoins
  que les ingrédients frais ne couvrent pas toujours seuls.</p>

  <h2>Repas frais ou croquettes : ce qui change dans la gamelle</h2>
  <div class="maquette-table-wrap">
  <table>
   <thead><tr><th>Critère</th><th>Repas frais Elmut</th><th>Croquettes industrielles</th></tr></thead>
   <tbody>
    <tr><td>Qualité des ingrédients</td><td>Propres à la consommation humaine</td><td>Standard animal</td></tr>
    <tr><td>Cuisson</td><td>Cuisson douce à 90 °C, à la vapeur et sous vide</td><td>Généralement au-dessus de 120 °C</td></tr>
    <tr><td>Conservateurs et additifs technologiques</td><td>Aucun</td><td>Présents dans la plupart des croquettes</td></tr>
   </tbody>
  </table>
  </div>
  <p>La <a href="https://elmut.fr/le-frais">cuisson douce</a> préserve une grande partie des nutriments et
  l'humidité naturelle des aliments. Elle donne aussi une texture tendre et un petit jus de cuisson qui séduit les
  chiens les plus difficiles. Nos recettes sont également préparées sans légumineuses, qui peuvent réduire la
  digestibilité.</p>

  <h2>Comment fonctionne la livraison de repas frais pour chien ?</h2>
  <ol>
   <li><strong>Vous nous présentez votre chien</strong> : race, poids, stérilisation, niveau d'activité. Le
   questionnaire sert à calculer la ration dont il a besoin.</li>
   <li><strong>Nous cuisinons son plan</strong> : les portions sont calculées pour lui, et vous choisissez ses
   recettes parmi le poulet, le bœuf, la dinde, le porc et le poisson.</li>
   <li><strong>Vous recevez ses repas chez vous</strong> à la fréquence choisie, avec un abonnement sans
   engagement.</li>
  </ol>
  <p>Vous voulez d'abord voir s'il vide sa gamelle ? Vous pouvez
  <a href="https://elmut.fr/wizard/type">essayer nos repas frais pendant 2 semaines</a>.</p>

  <h2>Quel prix pour une nourriture fraîche pour chien ?</h2>
  <p>Le prix dépend du gabarit de votre chien et de la formule choisie :</p>
  <ul>
   <li><strong>Pension complète</strong> : tous ses repas sont Elmut.</li>
   <li><strong>Demi-pension</strong> : Elmut couvre une partie de sa ration.</li>
  </ul>
  <p>Le prix indicatif par jour se calcule en quelques secondes à partir de la race et du poids de votre chien.</p>

  <h2>Conserver les repas frais de votre chien</h2>
  <p>Nos repas se conservent au réfrigérateur et se consomment dans les 5 jours après ouverture du boudin. Grâce à
  notre procédé de pasteurisation sous vide, ils se gardent bien plus longtemps qu'un plat frais classique : la
  date limite est indiquée sur l'étiquette de chaque boudin. Si vous en avez trop, vous pouvez les congeler
  jusqu'à six mois, comme une viande destinée à la consommation humaine.</p>
 </div>
</section>
"""


if __name__ == "__main__":
    cached = CACHE / "rendered.html"
    source = cached.read_text(encoding="utf-8") if cached.exists() else asyncio.run(render())
    (ROOT / "index.html").write_text(build(source), encoding="utf-8")
    print("index.html écrit")
