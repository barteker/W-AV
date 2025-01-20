
require('dotenv').config();
const SpotifyWebApi = require('spotify-web-api-node');

// Load environment variables
const clientId = process.env.SPOTIFY_CLIENT_ID;
const clientSecret = process.env.SPOTIFY_CLIENT_SECRET;

// Create the api object with the credentials
const spotifyApi = new SpotifyWebApi({
  clientId: clientId,
  clientSecret: clientSecret,
  redirectUri: 'http://localhost:8888/callback'
});

// Retrieve an access token
spotifyApi.clientCredentialsGrant().then(
  function(data) {
    console.log('The access token is ' + data.body['access_token']);
    spotifyApi.setAccessToken(data.body['access_token']);
  },
  function(err) {
    console.log('Something went wrong when retrieving an access token', err);
  }
);

// Function to get the current playback state
function getCurrentPlayback() {
  spotifyApi.getMyCurrentPlaybackState()
    .then(function(data) {
      if (data.body && data.body.is_playing) {
        console.log('User is currently playing something!');
      } else {
        console.log('User is not playing anything, or doing so in private.');
      }
    }, function(err) {
      console.log('Something went wrong!', err);
    });
}

// Call the function to get the current playback state
getCurrentPlayback();