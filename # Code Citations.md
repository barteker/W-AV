# Code Citations

## License: unknown
https://github.com/Clushini/Ajilla-V1/tree/729c11e254d13c20839ce1291545dd6f0061ca49/services/index.js

```
clientCredentialsGrant().then(
     function(data) {
       console.log('The access token is ' + data.body['access_token']);
       spotifyApi.setAccessToken(data.body['access_token']);
     },
     function(err) {
       console.
```


## License: unknown
https://github.com/FranciscoTorreblanca/MusicMarket/tree/da3daf78d35ea54a75ee3ef9e1753b8dc582c260/helpers/spotify.js

```
console.log('The access token is ' + data.body['access_token']);
       spotifyApi.setAccessToken(data.body['access_token']);
     },
     function(err) {
       console.log('Something went wrong when retrieving an access token
```


## License: unknown
https://github.com/ic188002/Vinyl-Makert-Place/tree/eec6ccf76426c72678d3c0f36e0144bb531bfcc2/controllers/records.js

```
' + data.body['access_token']);
       spotifyApi.setAccessToken(data.body['access_token']);
     },
     function(err) {
       console.log('Something went wrong when retrieving an access token', err);
     }
   );

   /
```


## License: unknown
https://github.com/Hekski/u09-frontend/tree/e8ecf5afe9e5fc32670e9c81d0f59e345fc3f5cc/src/services/spotifyRequests.js

```
body && data.body.is_playing) {
           console.log('User is currently playing something!');
         } else {
           console.log('User is not playing anything, or doing so in private.');
         }
       }, function(err) {
```

