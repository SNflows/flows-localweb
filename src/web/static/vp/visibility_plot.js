class VisibilityPlot {

    constructor(container, name, ra, dec) {

        this.container = container;

        $processor.init();

        this.sun = $moshier.body.sun;
        this.moon = $moshier.body.moon;

        let hmsRa = $moshier.util.hms(ra / 180 * Math.PI);
        let dmsDec = $moshier.util.dms(dec / 180 * Math.PI);
        let hmsDec = {
                hours: Math.sign(dec) * dmsDec.degree,
                minutes: Math.sign(dec) * dmsDec.minutes,
                seconds: Math.sign(dec) * dmsDec.seconds
        };

        this.target = {
                name: name, hmsRa: hmsRa, hmsDec: hmsDec,
                raMotion: 1e-21, decMotion: 0, velocity: 0,
                epoch: 2000, ra: 0.0, dec: 0.0, magnitude: 0,
                parallax: 0, equinox: {julian: 0.0}
        }

        this.setObservatory(observatories[0].name);
    }

    setObservatory = (observatory) => {

        let i = observatories.map(function(observatory) { return observatory.name; }).indexOf(observatory);
        if (i < 0) return;

        this.selected_observatory = observatory;

        $const.tlong = observatories[i].longitude;
        $const.glat = observatories[i].latitude;
        $const.height = observatories[i].elevation;

        this.newPlot();
    }

    getData = () => {

        let data = {
            time: new Array(),
            target: {
                alt: new Array(),
                az: new Array(),
                moon_sep: new Array(),
            },
            sun: {
                alt: new Array(),
                az: new Array(),
            },
            moon: {
                alt: new Array(),
                az: new Array(),
                lum: new Array(),
            },
            n: 0,
        };

        for (let t=0; t<24*60; t+=10) {

            let date = new Date();
            date.setMinutes(date.getMinutes() + t);

            $processor.calc(this.date2ephem(date), this.target);
            $processor.calc(this.date2ephem(date), this.sun);
            $processor.calc(this.date2ephem(date), this.moon);

            data.time.push(this.date2plotly(date));

            data.target.alt.push(this.target.position.altaz.topocentric.altitude);
            data.target.az.push(this.target.position.altaz.topocentric.azimuth);
            data.target.moon_sep.push(this.angularSeparation(this.target, this.moon));

            data.sun.alt.push(this.sun.position.altaz.topocentric.altitude);
            data.sun.az.push(this.sun.position.altaz.topocentric.azimuth);

            data.moon.alt.push(this.moon.position.altaz.topocentric.altitude);
            data.moon.az.push(this.moon.position.altaz.topocentric.azimuth);
            data.moon.lum.push(100 * this.moon.position.illuminatedFraction);

            data.n += 1;
        }

        return data;
    }

    newPlot = () => {

        let data = this.getData();

        let twilight = {
            x: data.time, y: data.sun.alt.map(function(alt) { return 90 * (alt < 0); }),
            fill: "tozeroy", fillcolor: "rgba(0,0,0,.1)", opacity: 0.1,
            line: {width: 0}, showlegend: false, hoverinfo: "skip",
        };

        let night = {
            x: data.time, y: data.sun.alt.map(function(alt) { return 90 * (alt < -18); }),
            fill: "tozeroy", fillcolor: "rgba(0,0,0,.1)", opacity: 0.1,
            line: {width: 0}, showlegend: false, hoverinfo: "skip",
        };

        let sun = {
            name: "Sun", x: data.time, y: data.sun.alt,
            type: "lines", line: {shape: "spline", dash: "dash", color: "#ff7f0e"},
            hovertemplate: "<b>Time</b>: <i>%{x}</i><br /><b>Altitude</b>: %{y:.2f}&#176;<br />%{text}",
            text: [...Array(data.n).keys()].map(function(i) {
                    return "<b>Azimuth</b>: " + data.sun.az[i].toFixed(2) + "&#176;";
            }),
        };

        let moon = {
            name: "Moon", x: data.time, y: data.moon.alt,
            type: "lines", line: {shape: "spline", dash: "dash", color: "#2ca02c"},
            hovertemplate: "<b>Time</b>: <i>%{x}</i><br /><b>Altitude</b>: %{y:.2f}&#176;<br />%{text}",
            text: [...Array(data.n).keys()].map(function(i) {
                    return "<b>Azimuth</b>: " + data.moon.az[i].toFixed(2) + "&#176;<br />Illuminated: " + data.moon.lum[i].toFixed(2) + "%";
            }),
        };

        let target = {
            name: this.target.name, x: data.time, y: data.target.alt,
            type: "lines", line: {shape: "spline", color: "#1f77b4"},
            hovertemplate: "<b>Time</b>: <i>%{x}</i><br /><b>Altitude</b>: %{y:.2f}&#176;<br />%{text}",
            text: [...Array(data.n).keys()].map(function(i) {
                    return "<b>Azimuth</b>: " + data.target.az[i].toFixed(2) + "&#176;<br />Moon separation: " + data.target.moon_sep[i].toFixed(2) + "&#176;";
            }),
        };

        let layout = {
            showlegend: true,
            xaxis: {
                title: "Time [UTC]",
                mirror: "ticks", linewidth: 1,
                dtick: 86400000 * 3/24, fixedrange: true,
            },
            yaxis: {
                title: "Altitude [degrees]",
                mirror: "ticks", linewidth: 1,
                dtick: 10, range: [0, 90], fixedrange: true,
            },
            updatemenus: [{
                active: observatories.map(function(observatory) { return observatory.name; }).indexOf(this.selected_observatory),
                name: "observatories", x: .5, y: 1.15,
                xanchor: "center", font: {size: 20},
                buttons: observatories.map(function(observatory) {
                        return {method: "skip", label: observatory.name};
                }),
            }],
            paper_bgcolor: '#d5d5d5',
        };

        Plotly.newPlot(this.container, [twilight, night, target, sun, moon], layout, {displayModeBar: true});

        let visibility_plot = this;
        let observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.attributeName == "data-unformatted" & mutation.target.__data__.name == "observatories") {
                    if (mutation.target.textContent != visibility_plot.selected_observatory) {
                        let observatory = mutation.target.textContent;
                        visibility_plot.setObservatory(observatory);
                    }
                }
            });
        });

        let observables = document.querySelector(".updatemenu-item-text");
        observer.observe(observables, {attributes: true});
    }

    date2ephem = (date) => {

        date = {
                year: date.getUTCFullYear(),
                month: date.getUTCMonth() + 1,
                day: date.getUTCDate(),
                hours: date.getUTCHours(),
                minutes: date.getUTCMinutes(),
                seconds: date.getUTCSeconds()
        };

        return date;
    }

    date2plotly = (date) => {

        date = String(date.getUTCFullYear()) + '-' +
                String(date.getUTCMonth() + 1).padStart(2, "0") + '-' +
                String(date.getUTCDate()).padStart(2, "0") + ' ' +
                String(date.getUTCHours()).padStart(2, "0") + ':' +
                String(date.getUTCMinutes()).padStart(2, "0") + ':' +
                String(date.getUTCSeconds()).padStart(2, "0")

        return date;
    }

    angularSeparation = (object1, object2) => {

        let alt1 = object1.position.altaz.topocentric.altitude / 180 * Math.PI;
        let az1 = object1.position.altaz.topocentric.azimuth / 180 * Math.PI;
        let alt2 = object2.position.altaz.topocentric.altitude / 180 * Math.PI;
        let az2 = object2.position.altaz.topocentric.azimuth / 180 * Math.PI;

        return Math.acos(Math.sin(alt1) * Math.sin(alt2) + Math.cos(alt1) * Math.cos(alt2) * Math.cos(az1 - az2)) / Math.PI * 180;
    }
}
