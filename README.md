# DocuSign eSign API - Guide de déploiement et d'utilisation

[![DocuSign](https://img.shields.io/badge/DocuSign-eSign-orange?logo=docusign)](https://www.docusign.com/)

API Flask permettant d’envoyer des PDF à signer via DocuSign.

---

## 1. Mise à jour de VPS

```bash
sudo apt update && sudo apt upgrade -y
```

## 2. Installation de docker

### Ajouter le repo Docker

```bash
sudo apt-get install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
```

### Installer Docker

```bash
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y
sudo systemctl status docker  # Vérifier le statut
sudo systemctl start docker   # Démarrer si nécessaire
sudo docker run hello-world   # Test rapide
```

## 3. Initialisation DocuSign eSign

Si vous n'avez pas d'intégration DocuSign eSign :

1. Créez une application intégrée sur [DocuSign Developer](https://developers.docusign.com/).  
2. Allez dans **My Apps & Keys** -> **Add App and Integration Key**.  
3. Donnez un nom à votre application.
4. Choisissez **Private custom integration**.
5. Dans **Is your application able to securely store a client secret?** cocher **Yes**.
6. Dans **Service Integration**, générez une paire de clés RSA :
   - Copiez la clé publique dans un fichier `public.pem`
   - Copiez la clé privée dans un fichier `private.pem`
7. Dans **Additional settings**, ajoutez une **Redirect URI** :

   ``` bash
   https://www.google.com
   ```

8. Autorisez la méthode HTTP **POST**.
9. Enregistrez votre application.

## 4. Consentement DocuSign

Pour finaliser l’intégration DocuSign, vous devez accepter le consentement OAuth :

1. Remplacez {your_integration_id} par l’ID d’intégration DocuSign que vous avez créé dans l'URl suivante.

   ``` bash
   https://account-d.docusign.com/oauth/auth?response_type=code&scope=signature%20impersonation&client_id={your_integration_id}&redirect_uri=https://www.google.com
   ```

2. Ouvrez cette URL dans votre navigateur et suivez les instructions pour accepter le consentement.
   > Le consentement DocuSign n'est à faire **qu'une seule fois par utilisateur de l'application** pour initialiser l'accès via votre compte.

## 5. Mise en place du serveur API

### Firewall UFW

```bash
sudo apt install ufw -y
sudo ufw allow 22 # Si vous utilisez SSH
sudo ufw allow 80
sudo ufw allow 5001
sudo ufw enable
```

### Cloner le dépôt

```bash
git clone https://github/AnakinGig/DocuSignApi
cd DocuSignApi
```

### Sécuriser la clé privée DocuSign

Copiez votre clée privée `private.pem` à la racine du projet.

Créez un secret Docker avec cette clé :

```bash
sudo docker swarm init # Initialiser le mode swarm si ce n'est pas déjà fait
sudo docker secret create docusign_private_key private.pem
sudo rm private.pem
```

### Déploiement avec Docker

```bash
sudo docker build -f dockerfile.prod -t docusign-api:prod .
sudo docker stack deploy -c docker-compose.prod.yml docusign_stack
```

Le serveur tourne ensuite sur port 5001.

## 6. Comment utiliser l’API

Votre application cliente (webshop, bot, React, PHP…) doit envoyer :

- un fichier PDF (file)
- les infos du signataire (email, name)
- la configuration d’intégration (integrator_key, user_id, account_id, private_key_b64)

### Example cURL

```bash
curl -X POST https://votre-domaine.com/api/send-pdf \
  -F "file=@document.pdf" \
  -F "email=test@demo.com" \
  -F "name=Nom Prenom" \
  -F "integrator_key=xxxx" \
  -F "user_id=xxxx" \
  -F "account_id=xxxx" \
```

Integrator_key : Clé d’intégration DocuSign de l'intégration  
User_id : ID utilisateur DocuSign
Account_id : ID compte DocuSign

## 7. Résultat

L'API renvoie :

```json
{
  "envelope_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

Vous pouvez suivre la signature dans votre tableau de bord DocuSign.
