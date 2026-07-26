# Examples

Entity IDs can differ if Home Assistant resolves a naming collision.

## Points dashboard

```yaml
type: entities
title: Nutri Points
entities:
  - sensor.nutri_remaining_points
  - sensor.nutri_budget_points
  - sensor.nutri_food_points
  - sensor.nutri_activity_points
  - binary_sensor.nutri_points_low
  - binary_sensor.nutri_over_budget
  - binary_sensor.nutri_weigh_in_due
```

## Low-points notification

```yaml
alias: Nutri Points running low
triggers:
  - trigger: state
    entity_id: binary_sensor.nutri_points_low
    to: "on"
actions:
  - action: notify.notify
    data:
      message: >-
        {{ states('sensor.nutri_remaining_points') }} points remain today.
```

## Log steps

```yaml
action: nutri_points.set_steps
data:
  steps: 9000
  mode: replace_total
```

Write actions continue to accept the legacy optional `entry_id` field, but it is unnecessary
when exactly one Nutri Points server is loaded.

## ESPHome food scale

Nutri Points starts weighing sessions. This Home Assistant automation forwards the immutable
nutrition snapshot and calculation descriptor to an ESPHome node:

```yaml
alias: Send Nutri Points session to kitchen scale
triggers:
  - trigger: nutri_points
    type: food_weighing_session_started
    entry_id: YOUR_NUTRI_POINTS_CONFIG_ENTRY_ID
actions:
  - action: esphome.kitchen_scale_start_food_weighing
    data:
      session_id: "{{ trigger.id }}"
      expires_at_epoch: "{{ as_timestamp(trigger.expires_at) | int }}"
      calculation_version: "{{ trigger.points_calculation.version }}"
      basis_grams: "{{ trigger.nutrition_per_100g.basis_grams }}"
      protein_per_100g: "{{ trigger.nutrition_per_100g.protein_g }}"
      carbs_per_100g: "{{ trigger.nutrition_per_100g.carbs_g }}"
      fat_per_100g: "{{ trigger.nutrition_per_100g.fat_g }}"
      fiber_per_100g: "{{ trigger.nutrition_per_100g.fiber_g }}"
      protein_coefficient: "{{ trigger.points_calculation.protein_coefficient }}"
      carbs_coefficient: "{{ trigger.points_calculation.carbs_coefficient }}"
      fat_coefficient: "{{ trigger.points_calculation.fat_coefficient }}"
      fiber_coefficient: "{{ trigger.points_calculation.fiber_coefficient }}"
      divisor: "{{ trigger.points_calculation.divisor }}"
      fiber_cap_g: "{{ trigger.points_calculation.fiber_cap_g }}"
      macro_decimal_places: "{{ trigger.points_calculation.macro_decimal_places }}"
      macro_rounding: "{{ trigger.points_calculation.macro_rounding }}"
      points_rounding: "{{ trigger.points_calculation.rounding }}"
      minimum_points: "{{ trigger.points_calculation.minimum_points }}"
```

The ESPHome side can retain that descriptor and calculate every scale update locally. Replace
`raw_scale_grams` with the ID of the filtered gram sensor provided by your HX711 or other scale
hardware:

```yaml
time:
  - platform: homeassistant
    id: homeassistant_time

globals:
  - id: weighing_active
    type: bool
    initial_value: "false"
  - id: weighing_session_id
    type: std::string
  - id: weighing_expires_at
    type: int
  - id: protein_100g
    type: float
  - id: carbs_100g
    type: float
  - id: fat_100g
    type: float
  - id: fiber_100g
    type: float
  - id: basis_grams
    type: float
  - id: protein_coefficient
    type: int
  - id: carbs_coefficient
    type: int
  - id: fat_coefficient
    type: int
  - id: fiber_coefficient
    type: int
  - id: points_divisor
    type: int
  - id: fiber_cap_g
    type: float
  - id: macro_decimal_places
    type: int
  - id: minimum_points
    type: int

api:
  actions:
    - action: start_food_weighing
      variables:
        session_id: string
        expires_at_epoch: int
        calculation_version: string
        basis_grams: float
        protein_per_100g: float
        carbs_per_100g: float
        fat_per_100g: float
        fiber_per_100g: float
        protein_coefficient: int
        carbs_coefficient: int
        fat_coefficient: int
        fiber_coefficient: int
        divisor: int
        fiber_cap_g: float
        macro_decimal_places: int
        macro_rounding: string
        points_rounding: string
        minimum_points: int
      then:
        - lambda: |-
            const bool supported =
              calculation_version == "food_points_macros_v1" &&
              macro_rounding == "half_even" &&
              points_rounding == "half_up";
            id(weighing_active) = supported;
            id(weighing_session_id) = session_id;
            id(active_weighing_session).publish_state(session_id);
            id(weighing_expires_at) = expires_at_epoch;
            id(basis_grams) = basis_grams;
            id(protein_100g) = protein_per_100g;
            id(carbs_100g) = carbs_per_100g;
            id(fat_100g) = fat_per_100g;
            id(fiber_100g) = fiber_per_100g;
            id(protein_coefficient) = protein_coefficient;
            id(carbs_coefficient) = carbs_coefficient;
            id(fat_coefficient) = fat_coefficient;
            id(fiber_coefficient) = fiber_coefficient;
            id(points_divisor) = divisor;
            id(fiber_cap_g) = fiber_cap_g;
            id(macro_decimal_places) = macro_decimal_places;
            id(minimum_points) = minimum_points;
            if (!supported) {
              id(projected_protein).publish_state(NAN);
              id(projected_carbs).publish_state(NAN);
              id(projected_fat).publish_state(NAN);
              id(projected_fiber).publish_state(NAN);
              id(projected_points).publish_state(NAN);
            }

text_sensor:
  - platform: template
    id: active_weighing_session
    name: Nutri Points session ID
    update_interval: never

sensor:
  - platform: template
    id: projected_protein
    name: Projected protein
    unit_of_measurement: g
    update_interval: never
  - platform: template
    id: projected_carbs
    name: Projected carbohydrates
    unit_of_measurement: g
    update_interval: never
  - platform: template
    id: projected_fat
    name: Projected fat
    unit_of_measurement: g
    update_interval: never
  - platform: template
    id: projected_fiber
    name: Projected fiber
    unit_of_measurement: g
    update_interval: never
  - platform: template
    id: projected_points
    name: Projected points
    accuracy_decimals: 0
    update_interval: never

  # Replace this template sensor with the filtered gram sensor from your scale.
  - platform: template
    id: raw_scale_grams
    internal: true
    update_interval: never
    on_value:
      then:
        - lambda: |-
            const auto now = id(homeassistant_time).now();
            const double grams = x;
            if (!id(weighing_active) || !now.is_valid() ||
                now.timestamp >= id(weighing_expires_at) ||
                !std::isfinite(grams) || grams < 0.0 || grams > 100000.0 ||
                id(basis_grams) <= 0.0) {
              id(projected_protein).publish_state(NAN);
              id(projected_carbs).publish_state(NAN);
              id(projected_fat).publish_state(NAN);
              id(projected_fiber).publish_state(NAN);
              id(projected_points).publish_state(NAN);
              return;
            }

            // nearbyint uses the default round-to-nearest, ties-to-even mode.
            const double factor = std::pow(10.0, id(macro_decimal_places));
            const auto scale_macro = [&](double per_basis) {
              return std::nearbyint((per_basis * grams / id(basis_grams)) * factor) / factor;
            };
            const double protein = scale_macro(id(protein_100g));
            const double carbs = scale_macro(id(carbs_100g));
            const double fat = scale_macro(id(fat_100g));
            const double fiber = scale_macro(id(fiber_100g));
            const double scored_fiber = std::min(fiber, static_cast<double>(id(fiber_cap_g)));
            const double raw_points =
              (protein * id(protein_coefficient) +
               carbs * id(carbs_coefficient) +
               fat * id(fat_coefficient) +
               scored_fiber * id(fiber_coefficient)) /
              id(points_divisor);
            const int points = std::max(
              id(minimum_points),
              static_cast<int>(std::floor(raw_points + 0.5)));

            id(projected_protein).publish_state(protein);
            id(projected_carbs).publish_state(carbs);
            id(projected_fat).publish_state(fat);
            id(projected_fiber).publish_state(fiber);
            id(projected_points).publish_state(points);
```

With the published v7 oats fixture, a 40 g reading produces 5 g protein, 24 g
carbohydrates, 2.8 g fat, 4 g fiber, and 3 points.

When the scale reports a stable reading, request an authoritative preview and then complete
the same session:

```yaml
alias: Complete stable Nutri Points scale reading
triggers:
  - trigger: state
    entity_id: binary_sensor.kitchen_scale_stable
    to: "on"
conditions:
  - condition: template
    value_template: "{{ states('text_sensor.kitchen_scale_nutri_points_session_id') | length > 0 }}"
actions:
  - action: nutri_points.preview_weighing_session
    data:
      session_id: "{{ states('text_sensor.kitchen_scale_nutri_points_session_id') }}"
      grams: "{{ states('sensor.kitchen_scale_weight') }}"
    response_variable: preview
  - condition: template
    value_template: "{{ preview.authoritative and preview.grams > 0 }}"
  - action: nutri_points.complete_weighing_session
    data:
      session_id: "{{ preview.session_id }}"
      grams: "{{ preview.grams }}"
    response_variable: completed_session
```
