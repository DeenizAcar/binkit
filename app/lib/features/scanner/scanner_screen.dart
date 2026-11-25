import 'dart:async';
import 'dart:isolate';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../result/result_screen.dart';
import 'frame_converter.dart';
import 'scan_pipeline.dart';
import 'scan_services.dart';

enum _CameraState { loading, ready, denied, unavailable }

class ScannerScreen extends StatefulWidget {
  const ScannerScreen({super.key});

  @override
  State<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends State<ScannerScreen>
    with WidgetsBindingObserver {
  CameraController? _controller;
  _CameraState _cameraState = _CameraState.loading;
  ScanServices? _services;
  bool _busy = false;
  String? _message;
  String? _hint;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initCamera();
    ScanServices.load().then((s) {
      if (mounted) {
        setState(() => _services = s);
      } else {
        s.dispose();
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    _services?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final controller = _controller;
    if (state == AppLifecycleState.inactive) {
      _controller = null;
      controller?.dispose();
      if (mounted) setState(() => _cameraState = _CameraState.loading);
    } else if (state == AppLifecycleState.resumed && controller == null) {
      _initCamera();
    }
  }

  Future<void> _initCamera() async {
    setState(() => _cameraState = _CameraState.loading);
    try {
      final cameras = await availableCameras();
      final back = cameras.where(
          (c) => c.lensDirection == CameraLensDirection.back);
      if (cameras.isEmpty) {
        setState(() => _cameraState = _CameraState.unavailable);
        return;
      }
      final controller = CameraController(
        back.isNotEmpty ? back.first : cameras.first,
        ResolutionPreset.high,
        enableAudio: false, // never record audio
        imageFormatGroup: ImageFormatGroup.yuv420,
      );
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() {
        _controller = controller;
        _cameraState = _CameraState.ready;
      });
    } on CameraException catch (e) {
      if (!mounted) return;
      final denied = e.code.contains('AccessDenied') ||
          e.code.contains('Permission');
      setState(() => _cameraState =
          denied ? _CameraState.denied : _CameraState.unavailable);
    }
  }

  /// Grabs exactly one frame from the image stream, in memory.
  ///
  /// takePicture() is deliberately not used: it writes a file to disk.
  Future<YuvFrame> _grabFrame(CameraController controller) async {
    final completer = Completer<YuvFrame>();
    final rotation = controller.description.sensorOrientation;
    await controller.startImageStream((image) {
      if (completer.isCompleted) return;
      try {
        completer.complete(YuvFrame.fromCameraImage(image, rotation));
      } catch (e, st) {
        completer.completeError(e, st);
      }
    });
    try {
      return await completer.future.timeout(const Duration(seconds: 3));
    } finally {
      await controller.stopImageStream();
    }
  }

  Future<void> _scan() async {
    final controller = _controller;
    final services = _services;
    if (controller == null || services == null || _busy) return;
    final l10n = AppLocalizations.of(context);

    setState(() {
      _busy = true;
      _message = null;
      _hint = null;
    });

    try {
      if (!services.pipeline.isReady) {
        _show(l10n.modelsUnavailable);
        return;
      }
      final frame = await _grabFrame(controller);
      final image = await Isolate.run(() => yuvFrameToImage(frame));
      final outcome = await services.pipeline.process(image);
      if (!mounted) return;

      switch (outcome) {
        case ScanModelsUnavailable():
          _show(l10n.modelsUnavailable);
        case ScanRejectedPlateTooLarge():
          _show(l10n.plateTooLarge, l10n.plateTooLargeHint);
        case ScanUncertain():
          _show(l10n.uncertain, l10n.uncertainHint);
        case ScanSuccess():
          await Navigator.of(context).push(MaterialPageRoute<void>(
            builder: (_) => ResultScreen(
              result: outcome,
              price: services.prices.forBrand(outcome.top.label),
            ),
          ));
      }
    } catch (e) {
      debugPrint('Scan failed: $e');
      _show(l10n.scanFailed);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _show(String message, [String? hint]) {
    if (!mounted) return;
    setState(() {
      _message = message;
      _hint = hint;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      backgroundColor: Colors.black,
      body: switch (_cameraState) {
        _CameraState.loading => _CenteredStatus(text: l10n.loadingCamera, progress: true),
        _CameraState.denied => _CenteredStatus(
            text: l10n.cameraPermissionDenied,
            actionLabel: l10n.tryAgain,
            onAction: _initCamera,
          ),
        _CameraState.unavailable => _CenteredStatus(
            text: l10n.cameraUnavailable,
            actionLabel: l10n.tryAgain,
            onAction: _initCamera,
          ),
        _CameraState.ready => _buildCamera(l10n),
      },
    );
  }

  Widget _buildCamera(AppLocalizations l10n) {
    final controller = _controller!;
    final theme = Theme.of(context);
    return Stack(
      fit: StackFit.expand,
      children: [
        Center(child: CameraPreview(controller)),
        const _FrameGuide(),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                _Banner(
                  title: _message ?? l10n.aimHint,
                  subtitle: _hint,
                  emphasized: _message != null,
                ),
                const Spacer(),
                _ScanButton(
                  label: _busy ? l10n.scanning : l10n.scanButton,
                  busy: _busy,
                  enabled: _services != null,
                  onPressed: _scan,
                ),
                const SizedBox(height: 12),
                Text(
                  l10n.privacyNote,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: Colors.white70),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _CenteredStatus extends StatelessWidget {
  const _CenteredStatus({
    required this.text,
    this.progress = false,
    this.actionLabel,
    this.onAction,
  });

  final String text;
  final bool progress;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (progress) ...[
              const CircularProgressIndicator(),
              const SizedBox(height: 16),
            ],
            Text(text,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white)),
            if (actionLabel != null) ...[
              const SizedBox(height: 16),
              FilledButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.title, this.subtitle, this.emphasized = false});

  final String title;
  final String? subtitle;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: emphasized
            ? scheme.primary.withValues(alpha: 0.92)
            : Colors.black.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              color: emphasized ? scheme.onPrimary : Colors.white,
              fontWeight: FontWeight.w700,
              fontSize: 16,
            ),
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 4),
            Text(subtitle!,
                style: TextStyle(
                    color: emphasized ? scheme.onPrimary : Colors.white70)),
          ],
        ],
      ),
    );
  }
}

class _FrameGuide extends StatelessWidget {
  const _FrameGuide();

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Center(
        child: FractionallySizedBox(
          widthFactor: 0.86,
          heightFactor: 0.32,
          child: DecoratedBox(
            decoration: BoxDecoration(
              border: Border.all(color: Colors.white54, width: 2),
              borderRadius: BorderRadius.circular(16),
            ),
          ),
        ),
      ),
    );
  }
}

class _ScanButton extends StatelessWidget {
  const _ScanButton({
    required this.label,
    required this.busy,
    required this.enabled,
    required this.onPressed,
  });

  final String label;
  final bool busy;
  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: FilledButton.icon(
        onPressed: enabled && !busy ? onPressed : null,
        icon: busy
            ? SizedBox.square(
                dimension: 20,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: scheme.onPrimary),
              )
            : const Icon(Icons.center_focus_strong),
        label: Text(label,
            style: const TextStyle(
                fontSize: 18, fontWeight: FontWeight.w800, letterSpacing: 1)),
      ),
    );
  }
}
