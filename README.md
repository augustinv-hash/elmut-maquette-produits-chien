# Maquette SEO : elmut.fr/produits-chien

Maquette statique annotée de la page https://elmut.fr/produits-chien, avec les recommandations SEO datashake pour la requête « nourriture fraîche chien ». Démo en `noindex`, non destinée à être indexée.

- Encadrés verts : recommandations (Hn, alt des images, FAQ, contenu de bas de page).
- Contours pointillés verts : contenus modifiés ou ajoutés.
- Bouton « Masquer les recommandations » : affiche la page optimisée sans les annotations.

Source des recommandations : page Notion « Nourriture fraîche chien » (BDD Elmut <> datashake), partie Structure de l'article.

## Reconstruire

```bash
cd ~/Documents/CODE/seo-tools
.venv/bin/python ../elmut-maquette-produits-chien/scripts/build.py
```

Le script rend la page réelle avec Playwright (cache dans `scripts/cache/`, à supprimer pour forcer un nouveau rendu), retire le JavaScript et les traceurs, puis applique les recommandations.

Polices : Geist, Chango et Inter (licence OFL) sont copiées en local. PP Pangaia et Maison Neue, sous licence commerciale, sont remplacées par Playfair Display et Archivo. Les images restent servies par elmut.fr.
