from __future__ import annotations

import pytest

from thera.corpus import MBU_TO_ROYAL, ROYAL_TO_MBU, from_mbu_volume, to_mbu_volumes


def test_to_mbu_volumes_43_maps_to_88() -> None:
    assert to_mbu_volumes(43) == [88]


def test_to_mbu_volumes_25_maps_to_39_through_47() -> None:
    assert to_mbu_volumes(25) == list(range(39, 48))


def test_from_mbu_volume_88_maps_to_43() -> None:
    assert from_mbu_volume(88) == 43


def test_from_mbu_volume_45_maps_to_25() -> None:
    assert from_mbu_volume(45) == 25


def test_mbu_mapping_round_trips_every_pair() -> None:
    for royal, mbus in ROYAL_TO_MBU.items():
        for mbu in mbus:
            assert from_mbu_volume(mbu) == royal


def test_mbu_mapping_disjoint_invariant() -> None:
    forward_flatten = {mbu for mbus in ROYAL_TO_MBU.values() for mbu in mbus}

    assert len(MBU_TO_ROYAL) == 91
    assert len(forward_flatten) == 91


@pytest.mark.parametrize("royal_volume", [0, 46])
def test_to_mbu_volumes_rejects_out_of_range_royal_volume(royal_volume: int) -> None:
    with pytest.raises(ValueError):
        to_mbu_volumes(royal_volume)


def test_from_mbu_volume_rejects_out_of_range_mbu_volume() -> None:
    with pytest.raises(ValueError):
        from_mbu_volume(92)
