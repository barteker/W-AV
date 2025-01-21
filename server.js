require('dotenv').config();
const express = require('express');
const SpotifyWebApi = require('spotify-web-api-node');
const path = require('path');

const app = express();
app.use(express.json());
app.use(express.static('public'));

const spotifyApi = new SpotifyWebApi({
    clientId: process.env.SPOTIFY_CLIENT_ID,
    clientSecret: process.env.SPOTIFY_CLIENT_SECRET,
    redirectUri: 'http://localhost:8888/callback'  // Changed from 3000 to 8888
});

let deviceId = null;

app.get('/login', (_, res) => {
    const scopes = ['streaming', 'user-read-playback-state', 'user-modify-playback-state'];
    res.redirect(spotifyApi.createAuthorizeURL(scopes, 'state'));
});

app.get('/callback', async (req, res) => {
    try {
        const data = await spotifyApi.authorizationCodeGrant(req.query.code);
        const { access_token, refresh_token } = data.body;
        
        spotifyApi.setAccessToken(access_token);
        spotifyApi.setRefreshToken(refresh_token);
        
        // Inject token into player page
        res.redirect(`/?token=${access_token}`);
    } catch (error) {
        res.status(500).send(`Authentication failed: ${error.message}`);
    }
});

app.post('/register-device', (req, res) => {
    deviceId = req.body.device_id;
    res.sendStatus(200);
});

app.post('/play', async (req, res) => {
    try {
        await spotifyApi.transferMyPlayback([deviceId], { play: true });
        res.sendStatus(200);
    } catch (err) {
        res.status(500).send(err);
    }
});

app.get('/refresh-token', async (_, res) => {
    try {
        const data = await spotifyApi.refreshAccessToken();
        const { access_token } = data.body;
        spotifyApi.setAccessToken(access_token);
        res.json({ token: access_token });
    } catch (error) {
        res.status(500).json({ error: 'Failed to refresh token' });
    }
});

const PORT = 8888;  // Changed from 3000 to 8888
app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log('Visit http://localhost:8888/login to start');
});