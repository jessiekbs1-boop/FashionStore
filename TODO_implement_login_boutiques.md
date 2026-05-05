# TODO: Implémenter système de login pour boutiques

- [x] Modifier models.py : rendre Shop.nom unique
- [x] Modifier routes/auth_routes.py : permettre login avec nom boutique pour admin
- [x] Modifier routes/auth_routes.py : dans register, créer Shop pour role admin
- [x] Modifier routes/vendeur_routes.py : filtrer données par current_user.shop_id au lieu de vendeur_id
- [x] Modifier templates/login.html : changer label à "Email ou Nom Boutique"
- [x] Modifier templates/register.html : ajouter champ nom boutique pour role admin
- [x] Tester : exécuter `python app.py`, créer admin avec shop, login avec nom boutique
