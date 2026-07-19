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

Write actions support an optional `entry_id` when more than one Nutri Points server is configured.
