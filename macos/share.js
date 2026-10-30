// Shows the macOS share menu for one file, next to the mouse pointer.
// Run with: osascript -l JavaScript share.js /path/to/file
// Used by mediaharvester.py because a web page can't open the native share menu itself.
ObjC.import("AppKit");

function run(argv) {
  const url = $.NSURL.fileURLWithPath(argv[0]);
  const app = $.NSApplication.sharedApplication;
  app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);

  const quit = () => $.NSApp.terminate(null);

  ObjC.registerSubclass({
    name: "MHShareDelegate",
    protocols: ["NSSharingServicePickerDelegate", "NSSharingServiceDelegate"],
    methods: {
      "sharingServicePicker:didChooseSharingService:": {
        types: ["void", ["id", "id"]],
        implementation: (picker, service) => {
          // Cancelled: nothing more to do. Otherwise stay alive until sharing finishes,
          // because sheets like Messages and Mail are hosted in this process.
          if (service.isNil()) quit();
          else service.delegate = delegate;
        },
      },
      "sharingService:didShareItems:": {
        types: ["void", ["id", "id"]],
        implementation: () => quit(),
      },
      "sharingService:didFailToShareItems:error:": {
        types: ["void", ["id", "id", "id"]],
        implementation: () => quit(),
      },
    },
  });
  const delegate = $.MHShareDelegate.alloc.init;

  // An invisible 1x1 window under the pointer anchors the menu where the person clicked Share
  const mouse = $.NSEvent.mouseLocation;
  const win = $.NSWindow.alloc.initWithContentRectStyleMaskBackingDefer(
    $.NSMakeRect(mouse.x, mouse.y, 1, 1), $.NSWindowStyleMaskBorderless, $.NSBackingStoreBuffered, false);
  win.opaque = false;
  win.backgroundColor = $.NSColor.clearColor;
  win.level = $.NSPopUpMenuWindowLevel;
  win.makeKeyAndOrderFront(null);
  app.activateIgnoringOtherApps(true);

  const picker = $.NSSharingServicePicker.alloc.initWithItems($([url]));
  picker.delegate = delegate;
  picker.showRelativeToRectOfViewPreferredEdge(win.contentView.bounds, win.contentView, $.NSMinYEdge);

  // Safety net so a stuck share never leaves a stray process behind
  $.NSTimer.scheduledTimerWithTimeIntervalRepeatsBlock(900, false, () => quit());
  app.run;
}
