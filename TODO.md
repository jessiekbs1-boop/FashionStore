# TODO: Implémenter association boutique pour vendeurs et clients

- [x] Modifier templates/register.html : Afficher champ shop_nom pour vendeur et client, rendre required.
- [x] Modifier routes/auth_routes.py : Pour vendeur/client, vérifier shop_nom existe et associer shop_id.
- [ ] Tester : Inscrire admin, puis vendeur/client avec boutique existante, vérifier admin voit les utilisateurs.
- [ ] Tester modification produit par vendeur (déjà implémenté).
- [ ] Exécuter `python app.py` pour validation finale.
