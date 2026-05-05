# CinetPay Integration Guide

## Overview
La plateforme Fashion Store utilise CinetPay pour les paiements réels. Voici comment configurer l'API CinetPay.

## Étapes de configuration

### 1. Inscription à CinetPay
- Allez sur https://cinetpay.com
- Créez un compte marchand (Business Account)
- Complétez votre profil de marchand et vérifiez votre identité

### 2. Récupérer vos clés API
Une fois votre compte activé :
- Connectez-vous au dashboard CinetPay
- Naviguez vers **Settings** → **API Keys** ou **Developer Settings**
- Trouvez votre :
  - **API Key** (clé API secrète)
  - **Site ID** (identifiant unique de votre site)

### 3. Configuration de l'application

#### Fichier `.env`
Mettez à jour le fichier `.env` à la racine du projet :

```env
# CinetPay API credentials
CINETPAY_API_KEY=your_actual_api_key_here
CINETPAY_SITE_ID=your_site_id_here
```

Remplacez `your_actual_api_key_here` et `your_site_id_here` par les vraies valeurs de votre compte CinetPay.

### 4. URLs de retour et webhook

Lors de la configuration dans le dashboard CinetPay, ajoutez les URLs suivantes :

- **Return URL** (après paiement) :
  ```
  https://votre-domaine.com/client/paiement/cinetpay/retour/<payment_id>
  ```
  
- **Webhook URL** (notification serveur) :
  ```
  https://votre-domaine.com/client/paiement/cinetpay/webhook
  ```

## Flux de paiement

1. **Client choisit CinetPay** dans `templates/client/choisir_paiement.html`
2. **Création du paiement** : `traiter_paiement()` crée un enregistrement Payment avec `transaction_id`
3. **Redirection CinetPay** : `cinetpay_checkout()` redirige vers la plateforme CinetPay
4. **Paiement client** : L'utilisateur effectue le paiement sur CinetPay
5. **Retour** : Après paiement, CinetPay redirige vers `cinetpay_return()`
6. **Webhook** : CinetPay envoie une notification à `cinetpay_webhook()` pour confirmer
7. **Confirmation** : Le paiement et la commande sont marqués comme payés

## Statuts de paiement

- `en attente` : Paiement créé, en attente de CinetPay
- `paye` : Paiement confirmé par CinetPay
- `echoue` : Paiement rejeté

## Classes et modules

- **`utils/cinetpay.py`** : Classe `CinetPayAPI` pour l'intégration
  - `generate_payment_link()` : Génère un lien de paiement
  - `verify_payment()` : Vérifie le statut d'une transaction
  - `validate_webhook()` : Valide les signatures de webhook

- **`routes/client_routes.py`** : Routes de paiement
  - `traiter_paiement()` : Crée le paiement
  - `cinetpay_checkout()` : Redirige vers CinetPay
  - `cinetpay_return()` : Gère le retour après paiement
  - `cinetpay_webhook()` : Reçoit les notifications CinetPay

## Tests

Actuellement, les tests ne font pas de vrais appels à CinetPay. Pour tester :

1. **Environnement de test CinetPay** : Utilisez le mode test/sandbox de CinetPay
2. **Paiements de test** : CinetPay fourni des numéros de test

## Troubleshooting

### API Key vide
Si vous voyez "CinetPay not configured", vérifiez que `CINETPAY_API_KEY` et `CINETPAY_SITE_ID` sont configurés dans `.env`.

### Erreur d'authentification
Vérifiez que vos clés API sont correctes et à jour dans le dashboard CinetPay.

### Webhook non reçu
- Vérifiez que votre serveur est accessible de l'extérieur
- Vérifiez les logs de CinetPay pour les erreurs de livraison
- Assurez-vous que l'URL webhook est correctement configurée dans le dashboard CinetPay

## Documentation CinetPay
- https://cinetpay.com/developers
- Documentation API : https://docs.cinetpay.com
