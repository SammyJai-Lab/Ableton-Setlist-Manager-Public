$(document).ready(function() {
    let cuePoints = [];

    function loadCuePoints() {
        $.get('/get_cue_points', function(data) {
            cuePoints = data;
            const cueList = $('#cue-list');
            cueList.empty();
            data.forEach((cue, index) => {
                if (!cue[0].toLowerCase().includes('stop')) {
                    cueList.append(`<li class="collection-item" data-index="${index}">${cue[0]}</li>`);
                }
            });
        });
    }

    loadCuePoints();

    $('#cue-list').on('click', '.collection-item', function() {
        $('.collection-item').removeClass('active');
        $(this).addClass('active');
    });

    $('#play-button').click(function() {
        const selectedCue = $('.collection-item.active');
        if (selectedCue.length > 0) {
            const cueIndex = selectedCue.data('index');
            const cueName = selectedCue.text();
            $.ajax({
                url: '/play_song',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ cue_index: cueIndex, cue_points: cuePoints }),
                success: function(response) {
                    const startPos = response.start_pos;
                    if (startPos !== null) {
                        $('#play-button').addClass('playing');
                        $('#now-playing').text(`Now playing: ${cueName}`);
                    }
                }
            });
        } else {
            M.toast({html: 'Please select a song from the setlist'});
        }
    });

    $('#stop-button').click(function() {
        $.post('/stop_song', function() {
            $('#play-button').removeClass('playing');
            $('#now-playing').text('');
            M.toast({html: 'Playback stopped'});
        });
    });

    function monitorPlayhead(stopPos) {
        $.ajax({
            url: '/monitor_playhead',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ stop_pos: stopPos }),
            success: function(response) {
                $('#play-button').removeClass('playing');
                $('#now-playing').text('');
                M.toast({html: 'Playback stopped'});
            }
        });
    }
});
