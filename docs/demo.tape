Output assets/demo.gif
Set FontSize 15
Set Width 1000
Set Height 480
Set Theme "Dracula"
Set Padding 20

Type "zhicast build examples/sample_script.md -o out/ --tts-provider stub"
Enter
Sleep 18s

Type "ls -lh out/"
Enter
Sleep 2s

Type "ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 out/video.mp4"
Enter
Sleep 2s
