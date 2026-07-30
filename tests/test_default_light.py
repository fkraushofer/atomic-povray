import pytest

from atomic_povray import Camera, get_default_light


def test_default_light_is_above_and_right_of_camera():
    camera = Camera.orthographic(
        direction=(0.0, 100.0, 0.0),
        target=(5.0, 0.0, 25.0),
        up=(0.0, 0.0, 1.0),
    )

    light = get_default_light(camera)

    assert light.location == pytest.approx((55.0, -100.0, 75.0))
    assert light.target == camera.target
    assert light.intensity == 1.8
    assert light.angular_diameter == 35.0
    assert light.samples == (9, 9)
    assert light.adaptive == 3


def test_default_light_passes_area_light_settings_through():
    camera = Camera.perspective(
        direction=(0.0, 0.0, -10.0),
        target=(0.0, 0.0, 0.0),
    )

    light = get_default_light(
        camera,
        intensity=2.3,
        angular_diameter=20.0,
        samples=(5, 7),
        adaptive=1,
    )

    assert light.location == pytest.approx((5.0, 5.0, 10.0))
    assert light.intensity == 2.3
    assert light.angular_diameter == 20.0
    assert light.samples == (5, 7)
    assert light.adaptive == 1


@pytest.mark.parametrize(
    ("direction", "up", "message"),
    (
        ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), "direction"),
        ((0.0, 0.0, -1.0), (0.0, 0.0, 2.0), "up"),
    ),
)
def test_default_light_rejects_degenerate_camera_axes(direction, up, message):
    camera = Camera.perspective(direction=direction, target=(0.0, 0.0, 0.0), up=up)

    with pytest.raises(ValueError, match=message):
        get_default_light(camera)
