var observatories = [
{% for observatory in observatories %}
    {name: "{{ observatory[0] }}", longitude: {{ observatory[1] }}, latitude: {{ observatory[2] }}, elevation: {{ observatory[3] }}},
{% endfor %}
]
